from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field

try:
    from backend.ai.groq_client import generate_report_details
except ModuleNotFoundError:
    from ai.groq_client import generate_report_details
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
DB_PATH = BASE_DIR / "data" / "trustagent.db"
RULES_PATH = BASE_DIR / "config" / "scoring_rules.json"

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
    score = int(rules.get("base_score", 75))

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
        negatives.append({"factor": factor, "delta": delta, "reason": reason, "source": "rules.v1", "confidence": confidence})
        evidence.append(
            {
                "factor": factor,
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
        positives.append({"factor": factor, "delta": delta, "reason": reason, "source": "rules.v1", "confidence": confidence})
        evidence.append(
            {
                "factor": factor,
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
    score = max(int(bounds["min"]), min(int(bounds["max"]), int(round(score))))
    data_state = "sufficient_data" if len(evidence) >= 4 else "limited_data"
    confidence_score = max(0.25, min(0.98, 0.45 + (len(evidence) * 0.06) - (0.05 * len(red_flags))))

    negatives_sorted = sorted(negatives, key=lambda x: x["delta"])[:3]
    positives_sorted = sorted(positives, key=lambda x: x["delta"], reverse=True)[:3]

    return {
        "score": score,
        "risk_level": _risk_level(score),
        "red_flags": list(dict.fromkeys(red_flags)),
        "factors": {"top_negative_factors": negatives_sorted, "top_positive_factors": positives_sorted},
        "evidence": evidence,
        "confidence_score": round(confidence_score, 3),
        "data_state": data_state,
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


def _persist_investigation(payload: dict[str, Any]) -> int:
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO investigations (
                created_at, target, category, trust_score, risk_level,
                red_flags_json, metrics_json, factors_json, evidence_json,
                report_text, target_normalized, confidence_score, data_state,
                ml_score, ai_meta_json, agent_pipeline_json, vector_doc_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    category_clean = category.strip().lower()

    if not target_clean:
        raise HTTPException(status_code=400, detail="target is required")
    if not category_clean:
        raise HTTPException(status_code=400, detail="category is required")

    created_at = utc_now_iso()
    pipeline_result = run_agent_pipeline(
        target=target_clean,
        category=category_clean,
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

    training_rows = _load_training_rows()
    ml_score, ml_meta = trust_model.predict(metrics, rule_score=int(scored["score"]), training_rows=training_rows)

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

    context_text = _build_context_text(
        target_clean,
        category_clean,
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
        "target_normalized": _normalize_target(target_clean),
        "category": category_clean,
        "trust_score": scored["score"],
        "ml_score": ml_score,
        "risk_level": scored["risk_level"],
        "red_flags": scored["red_flags"],
        "metrics": metrics,
        "why_score": scored["factors"],
        "evidence": scored["evidence"],
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
            "category": category_clean,
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


@app.post("/context/search")
def context_search(payload: ContextQueryRequest, _: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "vector_mode": vector_store.mode,
        "results": vector_store.query(payload.text, top_k=payload.top_k),
    }
