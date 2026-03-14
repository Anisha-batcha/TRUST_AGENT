from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field

try:
    from backend.ai.groq_client import generate_report_details
except ModuleNotFoundError:
    from ai.groq_client import generate_report_details
try:
    from backend.scam_patterns import detect_scam_patterns
except ModuleNotFoundError:
    from scam_patterns import detect_scam_patterns
try:
    from backend.agents import run_agent_pipeline
except ModuleNotFoundError:
    from agents import run_agent_pipeline
try:
    from backend.tasks import queue_adapter
except ModuleNotFoundError:
    from tasks import queue_adapter
try:
    from backend.security import jwt_manager, hash_password, verify_password
except ModuleNotFoundError:
    from security import jwt_manager, hash_password, verify_password
try:
    from backend.ml.trust_model import trust_model
except ModuleNotFoundError:
    from ml.trust_model import trust_model
try:
    from backend.vector_store import vector_store
except ModuleNotFoundError:
    from vector_store import vector_store


BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
DB_PATH = BASE_DIR / "data" / "trustagent.db"
RULES_PATH = BASE_DIR / "config" / "scoring_rules.json"

# Ensure local pip --target dependencies are importable even when the backend
# is started without the provided PowerShell scripts.
# NOTE: We intentionally avoid the legacy `.deps-backend` folder because it can
# contain partial/broken installs from earlier runs.
for rel in (".deps-backend-v2", ".deps-ai", ".deps-scrape"):
    candidate = (REPO_ROOT / rel).resolve()
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

# Ensure SQLite parent directory exists so first run works.
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

with RULES_PATH.open("r", encoding="utf-8") as fh:
    SCORING_RULES = json.load(fh)


class InvestigationRequest(BaseModel):
    target: str = Field(min_length=1)
    category: str = Field(min_length=1)


class CompareTarget(BaseModel):
    target: str = Field(min_length=1)
    category: str = Field(min_length=1)


class CompareRequest(BaseModel):
    left: CompareTarget
    right: CompareTarget
    persist: bool = True


class FeedbackRequest(BaseModel):
    scan_id: int = Field(ge=1)
    label: str = Field(min_length=2)
    notes: str | None = None


class AuthRequest(BaseModel):
    username: str = Field(min_length=3)
    password: str = Field(min_length=6)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3)
    password: str = Field(min_length=6)
    role: str = Field(default="analyst")


class AsyncInvestigationRequest(BaseModel):
    target: str = Field(min_length=1)
    category: str = Field(min_length=1)
    persist: bool = True


class ContextQueryRequest(BaseModel):
    text: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=10)


app = FastAPI(title="TrustAgent API", version="2.0.0")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_target(target: str) -> str:
    cleaned = target.strip().lower()
    cleaned = re.sub(r"https?://", "", cleaned)
    return cleaned.strip("/")


def _infer_category_from_target(target: str) -> str | None:
    t = target.strip().lower()
    if t.startswith("http://") or t.startswith("https://"):
        parsed = urlparse(t)
        host = (parsed.netloc or "").lower()
        # Remove credentials/port if present.
        if "@" in host:
            host = host.split("@", 1)[-1]
        if ":" in host:
            host = host.split(":", 1)[0]
        if host.startswith("www."):
            host = host[4:]

        host_map = {
            "instagram.com": "instagram",
            "x.com": "x",
            "twitter.com": "x",
            "linkedin.com": "linkedin",
            "youtube.com": "youtube",
            "youtu.be": "youtube",
            "facebook.com": "facebook",
            "t.me": "telegram",
            "telegram.me": "telegram",
        }
        for domain, cat in host_map.items():
            if host == domain or host.endswith(f".{domain}"):
                return cat
        return "website"

    # Non-URL inputs with a dot are likely a website/domain.
    if "." in t and " " not in t and "/" not in t:
        return "website"
    return None


def _hash_bucket(text: str, salt: str) -> float:
    import hashlib

    digest = hashlib.sha256(f"{salt}:{text}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _pick_range(base: str, salt: str, low: float, high: float) -> float:
    return low + (_hash_bucket(base, salt) * (high - low))


def _generate_metrics(target: str, category: str) -> dict[str, float]:
    seed = f"{_normalize_target(target)}|{category}"
    return {
        "engagement_rate": round(_pick_range(seed, "engagement", 0.005, 0.14), 4),
        "review_spike_ratio": round(_pick_range(seed, "review_spike", 0.05, 0.95), 3),
        "profile_completeness": round(_pick_range(seed, "profile", 0.35, 0.98), 3),
        "account_age_days": int(round(_pick_range(seed, "age", 3, 4200))),
        "sentiment_score": round(_pick_range(seed, "sentiment", 0.15, 0.92), 3),
        "follower_growth_consistency": round(_pick_range(seed, "growth", 0.1, 0.99), 3),
    }


def _risk_level(score: int) -> str:
    if score < 40:
        return "HIGH"
    if score < 70:
        return "MEDIUM"
    return "LOW"


def _score_investigation(target: str, category: str, metrics: dict[str, float]) -> dict[str, Any]:
    rules = SCORING_RULES
    base_score = int(rules.get("base_score", 75))
    score = base_score

    category_norm = (category or "").strip().lower()
    social_categories = {"instagram", "x", "linkedin", "youtube", "facebook", "telegram"}
    is_social = category_norm in social_categories

    negatives: list[dict[str, Any]] = []
    positives: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    red_flags: list[str] = []

    def add_negative(factor: str, delta: int, reason: str, signal: str, value: float | int, threshold: float | int, confidence: str = "medium") -> None:
        nonlocal score
        score += delta
        negatives.append(
            {
                "factor": factor,
                "delta": delta,
                "reason": reason,
                "signal": signal,
                "value": value,
                "threshold": threshold,
                "source": "rules.v1",
                "confidence": confidence,
            }
        )
        evidence.append(
            {
                "factor": factor,
                "delta": delta,
                "reason": reason,
                "signal": signal,
                "value": value,
                "threshold": threshold,
                "source": "rules.v1",
                "confidence": confidence,
                "last_verified_at": utc_now_iso(),
                "proof_url": target,
            }
        )

    def add_positive(factor: str, delta: int, reason: str, signal: str, value: float | int, threshold: float | int, confidence: str = "medium") -> None:
        nonlocal score
        score += delta
        positives.append(
            {
                "factor": factor,
                "delta": delta,
                "reason": reason,
                "signal": signal,
                "value": value,
                "threshold": threshold,
                "source": "rules.v1",
                "confidence": confidence,
            }
        )
        evidence.append(
            {
                "factor": factor,
                "delta": delta,
                "reason": reason,
                "signal": signal,
                "value": value,
                "threshold": threshold,
                "source": "rules.v1",
                "confidence": confidence,
                "last_verified_at": utc_now_iso(),
                "proof_url": target,
            }
        )

    if is_social:
        eng = metrics["engagement_rate"]
        eng_rules = rules["engagement"]
        if eng < eng_rules["very_low_threshold"]:
            add_negative("Engagement is critically low", eng_rules["very_low_delta"], "Interaction volume is abnormally low versus expected audience behavior.", "engagement_rate", eng, eng_rules["very_low_threshold"], "high")
            red_flags.append("Potential inorganic audience or inactive followers")
        elif eng < eng_rules["low_threshold"]:
            add_negative("Engagement below baseline", eng_rules["low_delta"], "Engagement is below common trust baseline for active entities.", "engagement_rate", eng, eng_rules["low_threshold"], "medium")
        elif eng > eng_rules["very_high_threshold"]:
            add_negative("Engagement spike is suspicious", eng_rules["very_high_delta"], "Very high engagement can indicate purchased interactions when unsupported by account maturity.", "engagement_rate", eng, eng_rules["very_high_threshold"], "medium")
            red_flags.append("Abnormal engagement pattern detected")
        else:
            add_positive("Engagement is healthy", 6, "Engagement sits in a normal operating range.", "engagement_rate", eng, eng_rules["low_threshold"], "medium")

    age_days = metrics["account_age_days"]
    age_rules = rules["age"]
    if age_days < age_rules["new_threshold"]:
        add_negative("Account is extremely new", age_rules["new_delta"], "Very recent accounts have limited behavioral history and elevated impersonation risk.", "account_age_days", age_days, age_rules["new_threshold"], "high")
        red_flags.append("Account created very recently")
    elif age_days < age_rules["young_threshold"]:
        add_negative("Account age is low", age_rules["young_delta"], "Limited history weakens confidence in identity continuity.", "account_age_days", age_days, age_rules["young_threshold"], "medium")
    elif age_days > age_rules["mature_threshold"]:
        add_positive("Long-lived identity", age_rules["mature_delta"], "Extended account history supports trust continuity.", "account_age_days", age_days, age_rules["mature_threshold"], "high")

    spike = metrics["review_spike_ratio"]
    rev_rules = rules["review"]
    if spike >= rev_rules["high_spike_threshold"]:
        add_negative("Review spike anomaly", rev_rules["high_spike_delta"], "Sudden concentrated review activity suggests inorganic behavior.", "review_spike_ratio", spike, rev_rules["high_spike_threshold"], "high")
        red_flags.append("Unnatural review spike")
    elif spike >= rev_rules["medium_spike_threshold"]:
        add_negative("Moderate review volatility", rev_rules["medium_spike_delta"], "Elevated review concentration reduces trust confidence.", "review_spike_ratio", spike, rev_rules["medium_spike_threshold"], "medium")
    else:
        add_positive("Review flow appears stable", 4, "No significant review burst patterns were detected.", "review_spike_ratio", spike, rev_rules["medium_spike_threshold"], "medium")

    completeness = metrics["profile_completeness"]
    prof_rules = rules["profile"]
    if completeness < prof_rules["critical_threshold"]:
        add_negative("Profile integrity is weak", prof_rules["critical_delta"], "Critical profile fields are missing or inconsistent.", "profile_completeness", completeness, prof_rules["critical_threshold"], "high")
        red_flags.append("Low profile completeness")
    elif completeness < prof_rules["low_threshold"]:
        add_negative("Profile completeness below confidence threshold", prof_rules["low_delta"], "Partial profile data weakens verification confidence.", "profile_completeness", completeness, prof_rules["low_threshold"], "medium")
    else:
        add_positive("Profile completeness is strong", 5, "Profile metadata quality supports identity confidence.", "profile_completeness", completeness, prof_rules["low_threshold"], "high")

    sentiment = metrics["sentiment_score"]
    if sentiment < 0.35:
        add_negative("Negative sentiment concentration", -8, "Sentiment trend is skewed negative.", "sentiment_score", sentiment, 0.35, "medium")
    elif sentiment > 0.75:
        add_positive("Positive sentiment baseline", 6, "Sentiment trend is consistently positive.", "sentiment_score", sentiment, 0.75, "medium")

    if is_social:
        growth_consistency = metrics["follower_growth_consistency"]
        if growth_consistency < 0.3:
            add_negative("Follower growth inconsistency", -9, "Growth behavior shows unstable velocity, a common manipulation signal.", "follower_growth_consistency", growth_consistency, 0.3, "medium")
            red_flags.append("Inconsistent follower growth")
        elif growth_consistency > 0.8:
            add_positive("Stable growth pattern", 4, "Follower growth trend appears consistent over time.", "follower_growth_consistency", growth_consistency, 0.8, "medium")

    bounds = rules["bounds"]
    score_raw = int(round(score))
    score = max(int(bounds["min"]), min(int(bounds["max"]), int(round(score))))
    data_state = "sufficient_data" if len(evidence) >= 4 else "limited_data"
    confidence_score = max(0.25, min(0.98, 0.45 + (len(evidence) * 0.06) - (0.05 * len(red_flags))))

    negatives_sorted = sorted(negatives, key=lambda x: x["delta"])[:3]
    positives_sorted = sorted(positives, key=lambda x: x["delta"], reverse=True)[:3]

    contributions = sorted([*positives, *negatives], key=lambda x: abs(int(x.get("delta", 0))), reverse=True)
    expected_signals = [
        "engagement_rate",
        "review_spike_ratio",
        "profile_completeness",
        "account_age_days",
        "sentiment_score",
        "follower_growth_consistency",
    ]
    missing_signals = [s for s in expected_signals if s not in metrics]
    present_signals = [s for s in expected_signals if s in metrics]
    coverage = round((len(present_signals) / max(1, len(expected_signals))) * 100.0, 1)

    confidence_counts = {"high": 0, "medium": 0, "low": 0}
    for item in contributions:
        band = str(item.get("confidence", "medium")).lower()
        if band not in confidence_counts:
            band = "medium"
        confidence_counts[band] += 1

    return {
        "score": score,
        "risk_level": _risk_level(score),
        "red_flags": list(dict.fromkeys(red_flags)),
        "factors": {"top_negative_factors": negatives_sorted, "top_positive_factors": positives_sorted},
        "evidence": evidence,
        "confidence_score": round(confidence_score, 3),
        "data_state": data_state,
        "xai": {
            "base_score": base_score,
            "rules_score_raw": score_raw,
            "rules_score": score,
            "was_clamped": score_raw != score,
            "clamp_min": int(bounds["min"]),
            "clamp_max": int(bounds["max"]),
            "signal_coverage_percent": coverage,
            "signals_present": present_signals,
            "signals_missing": missing_signals,
            "contributions": contributions,
            "confidence_counts": confidence_counts,
        },
    }


def _ensure_table_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, sql_type in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS investigations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            target TEXT NOT NULL,
            category TEXT NOT NULL,
            trust_score INTEGER NOT NULL,
            risk_level TEXT NOT NULL,
            red_flags_json TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            factors_json TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            report_text TEXT NOT NULL,
            target_normalized TEXT,
            confidence_score REAL,
            data_state TEXT,
            ml_score REAL,
            ai_meta_json TEXT,
            agent_pipeline_json TEXT,
            vector_doc_id TEXT
        )
        """
    )
    _ensure_table_columns(
        conn,
        "investigations",
        {
            "target_normalized": "TEXT",
            "confidence_score": "REAL",
            "data_state": "TEXT",
            "ml_score": "REAL",
            "ai_meta_json": "TEXT",
            "agent_pipeline_json": "TEXT",
            "vector_doc_id": "TEXT",
            "scam_patterns_json": "TEXT",
        },
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            scan_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            label TEXT NOT NULL,
            notes TEXT,
            target TEXT,
            target_normalized TEXT,
            category TEXT
        )
        """
    )
    _ensure_table_columns(
        conn,
        "feedback",
        {
            "target": "TEXT",
            "target_normalized": "TEXT",
            "category": "TEXT",
        },
    )
    conn.commit()


def _seed_default_admin(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            ("admin", hash_password("admin123"), "admin", utc_now_iso()),
        )
        conn.commit()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    _seed_default_admin(conn)
    return conn


def _row_get(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    return row[key] if key in row.keys() else default


def _row_to_investigation(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "scan_id": row["id"],
        "created_at": row["created_at"],
        "last_verified_at": row["created_at"],
        "target": row["target"],
        "target_normalized": _row_get(row, "target_normalized") or _normalize_target(row["target"]),
        "category": row["category"],
        "trust_score": row["trust_score"],
        "ml_score": float(_row_get(row, "ml_score") or row["trust_score"]),
        "risk_level": row["risk_level"],
        "red_flags": json.loads(row["red_flags_json"]),
        "metrics": json.loads(row["metrics_json"]),
        "why_score": json.loads(row["factors_json"]),
        "evidence": json.loads(row["evidence_json"]),
        "investigation_report": row["report_text"],
        "confidence_score": float(_row_get(row, "confidence_score") or 0.0),
        "data_state": _row_get(row, "data_state") or "sufficient_data",
        "agent_pipeline": json.loads(_row_get(row, "agent_pipeline_json") or "{}"),
        "ai_meta": json.loads(_row_get(row, "ai_meta_json") or "{}"),
        "scam_patterns": json.loads(_row_get(row, "scam_patterns_json") or "[]"),
        "vector_doc_id": _row_get(row, "vector_doc_id"),
    }


def _load_training_rows(limit: int = 400) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT metrics_json, trust_score FROM investigations ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            out.append({"metrics": json.loads(row["metrics_json"]), "trust_score": float(row["trust_score"])})
        except Exception:
            continue
    return out


def _feedback_stats(target_normalized: str, category: str) -> dict[str, Any]:
    label_counts = {"legit": 0, "scam": 0, "unknown": 0}
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT label, COUNT(*) AS c
            FROM feedback
            WHERE target_normalized = ? AND category = ?
            GROUP BY label
            """,
            (target_normalized, category.strip().lower()),
        ).fetchall()
    for r in rows:
        label = str(r["label"] or "").strip().lower()
        if label in label_counts:
            label_counts[label] = int(r["c"] or 0)
    total = sum(label_counts.values())
    return {"target_normalized": target_normalized, "category": category.strip().lower(), "total": total, **label_counts}


def _persist_investigation(payload: dict[str, Any]) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO investigations (
                created_at, target, category, trust_score, risk_level,
                red_flags_json, metrics_json, factors_json, evidence_json,
                report_text, target_normalized, confidence_score, data_state,
                ml_score, ai_meta_json, agent_pipeline_json, vector_doc_id,
                scam_patterns_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["created_at"],
                payload["target"],
                payload["category"],
                payload["trust_score"],
                payload["risk_level"],
                json.dumps(payload["red_flags"]),
                json.dumps(payload["metrics"]),
                json.dumps(payload["why_score"]),
                json.dumps(payload["evidence"]),
                payload["investigation_report"],
                payload["target_normalized"],
                payload["confidence_score"],
                payload["data_state"],
                float(payload.get("ml_score", payload["trust_score"])),
                json.dumps(payload.get("ai_meta", {})),
                json.dumps(payload.get("agent_pipeline", {})),
                payload.get("vector_doc_id"),
                json.dumps(payload.get("scam_patterns", [])),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def _build_context_text(target: str, category: str, metrics: dict[str, float], evidence: list[dict[str, Any]], scraped_text: str) -> str:
    key_evidence = "; ".join(f"{e.get('factor')}: {e.get('reason')}" for e in evidence[:3])
    return (
        f"Target={target}; Category={category}; "
        f"engagement={metrics.get('engagement_rate')}; spike={metrics.get('review_spike_ratio')}; "
        f"profile={metrics.get('profile_completeness')}; sentiment={metrics.get('sentiment_score')}; "
        f"evidence={key_evidence}; raw={scraped_text[:500]}"
    )


def _build_investigation_result(target: str, category: str, persist: bool = True) -> dict[str, Any]:
    target_clean = target.strip()
    requested_category = category.strip().lower()

    if not target_clean:
        raise HTTPException(status_code=400, detail="target is required")
    if not requested_category:
        raise HTTPException(status_code=400, detail="category is required")

    inferred = _infer_category_from_target(target_clean)
    effective_category = requested_category
    category_warning: str | None = None
    if inferred and inferred != requested_category:
        effective_category = inferred
        category_warning = f"Category mismatch for target URL; using '{effective_category}' instead of '{requested_category}'."

    created_at = utc_now_iso()
    pipeline_result = run_agent_pipeline(
        target=target_clean,
        category=effective_category,
        score_fn=_score_investigation,
        fallback_metrics_fn=_generate_metrics,
    )

    strict_data = (os.getenv("TRUSTAGENT_STRICT_DATA") or "").strip().lower() in {"1", "true", "yes", "on"}
    collector_mode = str(pipeline_result.pipeline.get("collector", {}).get("mode") or "")
    if strict_data and collector_mode == "fallback":
        raise HTTPException(
            status_code=503,
            detail="Insufficient live data for accurate scoring (scraping failed and synthetic fallback is disabled in strict mode).",
        )

    metrics = pipeline_result.metrics
    scored = pipeline_result.scored
    scam_patterns = detect_scam_patterns(pipeline_result.context_text or "", target_clean, effective_category)

    training_rows = _load_training_rows()
    ml_score, ml_meta = trust_model.predict(metrics, rule_score=int(scored["score"]), training_rows=training_rows)

    rule_score = int(scored["score"])
    blended_score = int(round((0.7 * int(scored["score"])) + (0.3 * ml_score)))
    scored["score"] = max(10, min(99, blended_score))
    scored["risk_level"] = _risk_level(scored["score"])
    scored["factors"]["top_positive_factors"].append(
        {
            "factor": "ML consensus calibration",
            "delta": int(scored["score"] - ml_score),
            "reason": f"RandomForest/heuristic ML score={ml_score} blended with rules score.",
            "source": "ml.random_forest.v1",
            "confidence": "medium",
        }
    )

    xai = dict(scored.get("xai") or {})
    if xai:
        xai["ml_score"] = ml_score
        xai["final_score"] = scored["score"]
        xai["blend_weights"] = {"rules": 0.7, "ml": 0.3}
        xai.setdefault("contributions", [])
        xai["contributions"] = [
            {
                "factor": "ML calibration blend",
                "delta": int(scored["score"] - rule_score),
                "reason": "Final score is blended from rules + RandomForest ML model.",
                "signal": "ml_blend",
                "value": ml_score,
                "threshold": rule_score,
                "source": "ml.random_forest.v1",
                "confidence": "medium",
            },
            *list(xai["contributions"]),
        ]
        scored["xai"] = xai

    target_normalized = _normalize_target(target_clean)
    feedback_meta = _feedback_stats(target_normalized, effective_category)
    feedback_adjustment = 0
    if (os.getenv("TRUSTAGENT_FEEDBACK_CALIBRATE") or "1").strip().lower() not in {"0", "false", "no"}:
        total_fb = int(feedback_meta.get("total") or 0)
        if total_fb >= 3:
            legit = int(feedback_meta.get("legit") or 0)
            scam = int(feedback_meta.get("scam") or 0)
            delta = int(round(((legit - scam) / max(1, total_fb)) * 12))
            if delta:
                feedback_adjustment = delta
                scored["score"] = max(10, min(99, int(scored["score"]) + delta))
                scored["risk_level"] = _risk_level(scored["score"])
                # Confidence boost when the community agrees strongly; otherwise slight penalty.
                agreement = max(legit, scam) / max(1, total_fb)
                if agreement >= 0.8:
                    scored["confidence_score"] = round(min(0.98, float(scored["confidence_score"]) + 0.05), 3)
                elif agreement <= 0.6:
                    scored["confidence_score"] = round(max(0.25, float(scored["confidence_score"]) - 0.03), 3)

                xai = dict(scored.get("xai") or {})
                if xai:
                    xai["final_score"] = scored["score"]
                    xai.setdefault("contributions", [])
                    xai["contributions"] = [
                        {
                            "factor": "Community feedback calibration",
                            "delta": delta,
                            "reason": f"{legit} legit vs {scam} scam labels out of {total_fb} feedback marks for this target.",
                            "signal": "feedback_loop",
                            "value": legit,
                            "threshold": scam,
                            "source": "feedback.loop.v1",
                            "confidence": "medium" if total_fb < 10 else "high",
                        },
                        *list(xai["contributions"]),
                    ]
                    scored["xai"] = xai

    feedback_meta["applied_delta"] = feedback_adjustment
    feedback_meta["enabled"] = (os.getenv("TRUSTAGENT_FEEDBACK_CALIBRATE") or "1").strip().lower() not in {"0", "false", "no"}

    context_text = _build_context_text(
        target_clean,
        effective_category,
        metrics,
        scored["evidence"],
        pipeline_result.context_text,
    )
    related = vector_store.query(context_text, top_k=3)
    related_contexts = [r.get("text", "")[:180] for r in related]

    report, ai_meta = generate_report_details(
        target_clean,
        scored["score"],
        scored["red_flags"],
        related_contexts=related_contexts,
    )

    result = {
        "scan_id": None,
        "created_at": created_at,
        "last_verified_at": created_at,
        "target": target_clean,
        "target_normalized": target_normalized,
        "category": effective_category,
        "requested_category": requested_category,
        "category_warning": category_warning,
        "trust_score": scored["score"],
        "ml_score": ml_score,
        "risk_level": scored["risk_level"],
        "red_flags": scored["red_flags"],
        "metrics": metrics,
        "why_score": scored["factors"],
        "evidence": scored["evidence"],
        "xai": scored.get("xai"),
        "scam_patterns": scam_patterns,
        "feedback_meta": feedback_meta,
        "investigation_report": report,
        "confidence_score": scored["confidence_score"],
        "data_state": scored["data_state"],
        "agent_pipeline": pipeline_result.pipeline,
        "ai_meta": ai_meta,
        "vector_mode": vector_store.mode,
        "related_contexts": related,
        "ml_meta": ml_meta,
    }

    doc_id = f"scan-{created_at}-{_normalize_target(target_clean)}"
    result["vector_doc_id"] = doc_id

    if persist:
        result["scan_id"] = _persist_investigation(result)
        result["vector_doc_id"] = f"scan-{result['scan_id']}"

    vector_store.upsert(
        result["vector_doc_id"],
        context_text,
        {
            "target": target_clean,
            "category": effective_category,
            "trust_score": result["trust_score"],
            "risk_level": result["risk_level"],
            "created_at": created_at,
        },
    )

    return result


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    try:
        payload = jwt_manager.decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    with _connect() as conn:
        row = conn.execute("SELECT id, username, role FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return {"id": row["id"], "username": row["username"], "role": row["role"]}


@app.get("/")
def health() -> dict[str, Any]:
    return {"status": "ok", "vector_mode": vector_store.mode, "queue_mode": queue_adapter.mode}


@app.post("/auth/token")
def issue_token(payload: AuthRequest) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT username, password_hash, role FROM users WHERE username = ?",
            (payload.username.strip(),),
        ).fetchone()

    if row is None or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    expires_hours = 24
    try:
        env_hours = int((os.getenv("JWT_EXPIRES_HOURS") or "").strip() or "24")
        expires_hours = max(1, min(24 * 30, env_hours))
    except Exception:
        expires_hours = 24

    token = jwt_manager.create_token(row["username"], expires_hours=expires_hours, extra={"role": row["role"]})
    return {"access_token": token, "token_type": "bearer", "expires_in": int(expires_hours * 3600)}


@app.post("/auth/register")
def register_user(payload: RegisterRequest) -> dict[str, Any]:
    username = payload.username.strip().lower()
    if username == "admin":
        raise HTTPException(status_code=400, detail="Reserved username")
    with _connect() as conn:
        exists = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="Username already exists")
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, hash_password(payload.password), "analyst", utc_now_iso()),
        )
        conn.commit()
    return {"status": "created", "username": username, "role": "analyst"}


@app.post("/investigate")
def investigate(payload: InvestigationRequest, _: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return _build_investigation_result(payload.target, payload.category, persist=True)


@app.post("/investigate/async")
def investigate_async(payload: AsyncInvestigationRequest, _: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    job_id = queue_adapter.submit(_build_investigation_result, payload.target, payload.category, payload.persist)
    return {"job_id": job_id, "status": "queued", "queue_mode": queue_adapter.mode}


@app.get("/jobs/{job_id}")
def get_job(job_id: str, _: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    job = queue_adapter.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/compare")
def compare(payload: CompareRequest, _: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    left_result = _build_investigation_result(payload.left.target, payload.left.category, persist=payload.persist)
    right_result = _build_investigation_result(payload.right.target, payload.right.category, persist=payload.persist)

    delta = left_result["trust_score"] - right_result["trust_score"]
    verdict = "LEFT_MORE_TRUSTED" if delta > 0 else "RIGHT_MORE_TRUSTED" if delta < 0 else "TIE"

    return {"left": left_result, "right": right_result, "score_delta": delta, "verdict": verdict}


@app.get("/investigations/{scan_id}")
def get_investigation(scan_id: int, _: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM investigations WHERE id = ?", (scan_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return _row_to_investigation(row)


@app.get("/history")
def history(
    target: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=500),
    _: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []

    if target:
        clauses.append("(target LIKE ? OR target_normalized LIKE ?)")
        like_pattern = f"%{target.strip()}%"
        params.extend([like_pattern, like_pattern])
    if category:
        clauses.append("category = ?")
        params.append(category.strip().lower())

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    query = f"SELECT * FROM investigations {where_sql} ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()

    investigations = [_row_to_investigation(row) for row in rows]
    timeline = [
        {
            "scan_id": item["scan_id"],
            "created_at": item["created_at"],
            "target": item["target"],
            "category": item["category"],
            "trust_score": item["trust_score"],
            "risk_level": item["risk_level"],
        }
        for item in investigations
    ]

    return {"count": len(investigations), "investigations": investigations, "timeline": list(reversed(timeline))}


@app.get("/analytics")
def analytics(limit: int = Query(default=10, ge=1, le=100), _: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with _connect() as conn:
        top_rows = conn.execute(
            """
            SELECT target, category, AVG(trust_score) AS avg_score, AVG(ml_score) AS avg_ml_score, COUNT(*) AS scans
            FROM investigations
            GROUP BY target, category
            HAVING scans > 0
            ORDER BY avg_score ASC, scans DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        trend_rows = conn.execute(
            """
            SELECT
                category,
                COUNT(*) AS total_scans,
                SUM(CASE WHEN risk_level = 'HIGH' THEN 1 ELSE 0 END) AS high_risk_count,
                AVG(trust_score) AS avg_score,
                AVG(ml_score) AS avg_ml_score
            FROM investigations
            GROUP BY category
            ORDER BY high_risk_count DESC, avg_score ASC
            """
        ).fetchall()

    top_risky_targets = [
        {
            "target": row["target"],
            "category": row["category"],
            "avg_score": round(float(row["avg_score"]), 2),
            "avg_ml_score": round(float(row["avg_ml_score"] or row["avg_score"]), 2),
            "scans": int(row["scans"]),
        }
        for row in top_rows
    ]

    category_trends = [
        {
            "category": row["category"],
            "total_scans": int(row["total_scans"]),
            "high_risk_count": int(row["high_risk_count"] or 0),
            "avg_score": round(float(row["avg_score"]), 2) if row["avg_score"] is not None else None,
            "avg_ml_score": round(float(row["avg_ml_score"]), 2) if row["avg_ml_score"] is not None else None,
        }
        for row in trend_rows
    ]

    return {"top_risky_targets": top_risky_targets, "category_trends": category_trends}


def _persist_feedback(username: str, payload: FeedbackRequest) -> dict[str, Any]:
    label = payload.label.strip().lower()
    if label not in {"legit", "scam", "unknown"}:
        raise HTTPException(status_code=400, detail="label must be one of: legit, scam, unknown")

    with _connect() as conn:
        row = conn.execute("SELECT id, target, category, target_normalized FROM investigations WHERE id = ?", (payload.scan_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Investigation not found")

        created_at = utc_now_iso()
        conn.execute(
            """
            INSERT INTO feedback (created_at, scan_id, username, label, notes, target, target_normalized, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                int(payload.scan_id),
                username,
                label,
                (payload.notes or "").strip() or None,
                row["target"],
                (row["target_normalized"] or _normalize_target(row["target"])),
                row["category"],
            ),
        )
        conn.commit()

    return {
        "created_at": created_at,
        "scan_id": int(payload.scan_id),
        "username": username,
        "label": label,
        "notes": (payload.notes or "").strip() or None,
    }


@app.post("/feedback")
def submit_feedback(payload: FeedbackRequest, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return _persist_feedback(user["username"], payload)


@app.get("/feedback")
def list_feedback(limit: int = Query(default=50, ge=1, le=500), _: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, created_at, scan_id, username, label, notes, target, target_normalized, category FROM feedback ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    items = [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "scan_id": r["scan_id"],
            "username": r["username"],
            "label": r["label"],
            "notes": r["notes"],
            "target": r["target"],
            "target_normalized": _row_get(r, "target_normalized"),
            "category": r["category"],
        }
        for r in rows
    ]
    return {"count": len(items), "items": items}


@app.post("/context/search")
def context_search(payload: ContextQueryRequest, _: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "vector_mode": vector_store.mode,
        "results": vector_store.query(payload.text, top_k=payload.top_k),
    }
