from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class ScamPattern:
    pattern_id: str
    label: str
    severity: str  # low | medium | high
    description: str
    keywords: tuple[str, ...]


PATTERNS: tuple[ScamPattern, ...] = (
    ScamPattern(
        pattern_id="urgent_action",
        label="Urgency / pressure tactics",
        severity="medium",
        description="Urgent language is common in scam funnels to reduce verification time.",
        keywords=("act now", "limited time", "hurry", "urgent", "immediately", "last chance"),
    ),
    ScamPattern(
        pattern_id="credential_harvest",
        label="Login / credential harvesting",
        severity="high",
        description="Requests to login/verify account or enter OTP/password are high risk when unexpected.",
        keywords=("verify your account", "confirm your account", "reset password", "one time password", "otp", "password"),
    ),
    ScamPattern(
        pattern_id="payment_push",
        label="Payment push / advance fee",
        severity="high",
        description="Pushes for advance payment or non-reversible payment methods.",
        keywords=("pay now", "advance payment", "processing fee", "activation fee", "upi", "gift card", "crypto", "bitcoin"),
    ),
    ScamPattern(
        pattern_id="giveaway_airdrop",
        label="Giveaway / airdrop bait",
        severity="high",
        description="Giveaway/airdrop and doubling-money claims frequently correlate with scams.",
        keywords=("giveaway", "airdrop", "double your", "free money", "claim reward", "winner"),
    ),
    ScamPattern(
        pattern_id="support_whatsapp",
        label="Support via WhatsApp/Telegram",
        severity="medium",
        description="Scam pages often route support to WhatsApp/Telegram numbers instead of official channels.",
        keywords=("whatsapp", "telegram", "dm us", "message us", "contact on whatsapp"),
    ),
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _host(target: str) -> str:
    t = (target or "").strip().lower()
    if not (t.startswith("http://") or t.startswith("https://")):
        return ""
    try:
        u = urlparse(t)
        host = (u.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if ":" in host:
            host = host.split(":", 1)[0]
        return host
    except Exception:
        return ""


def detect_scam_patterns(text: str, target: str, category: str) -> list[dict[str, Any]]:
    """
    Lightweight, rule-based scam pattern detector.
    This is additive (does NOT change trust_score) and is meant for explainability + triage.
    """
    normalized = _normalize_text(text)
    if not normalized:
        return []

    out: list[dict[str, Any]] = []
    host = _host(target)
    for pat in PATTERNS:
        hits = [kw for kw in pat.keywords if kw in normalized]
        if not hits:
            continue
        out.append(
            {
                **asdict(pat),
                "matched": hits[:6],
                "source": "rules.patterns.v1",
                "target_host": host,
                "category": (category or "").strip().lower(),
            }
        )

    # Deduplicate by pattern_id.
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in out:
        pid = str(item.get("pattern_id"))
        if pid and pid not in seen:
            seen.add(pid)
            deduped.append(item)
    return deduped

