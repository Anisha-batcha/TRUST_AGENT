from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
for rel in (".deps-ai", ".deps-backend-v2", ".deps-scrape"):
    candidate = (REPO_ROOT / rel).resolve()
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from groq import Groq
except Exception:  # pragma: no cover - optional dependency
    Groq = None

MODEL_CANDIDATES = [
    "llama3-70b-8192",
    "llama-3.3-70b-versatile",
    "llama3-8b-8192",
]

GROQ_OPENAI_URL = "https://api.groq.com/openai/v1/chat/completions"


def _fallback_report(target: str, score: int, flags: list[str], reason: str | None = None) -> str:
    if flags:
        return (
            f"Automated review for {target}: trust score is {score}/100. "
            f"Key risk signals detected: {', '.join(flags)}. "
            "Proceed with enhanced verification before any transaction."
        )
    return (
        f"Automated review for {target}: trust score is {score}/100 with no critical red flags. "
        "Maintain standard due diligence and monitor for behavior changes."
    )


def _build_prompt(target: str, score: int, flags: list[str], related_contexts: list[str] | None) -> str:
    ctx = "\n".join(f"- {c}" for c in (related_contexts or [])[:3])
    return (
        "Analyze the following digital entity security data.\n"
        f"Target: {target}\n"
        f"Trust Score: {score}/100\n"
        f"Flags: {', '.join(flags) if flags else 'None'}\n"
        f"Related Historical Context:\n{ctx if ctx else '- None'}\n\n"
        "Return exactly 3 concise sentences: current risk posture, likely behavioral reason, and one mitigation action."
    )


def generate_report_details(
    target: str,
    score: int,
    flags: list[str],
    related_contexts: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    global Groq
    if Groq is None:
        # Groq may have been installed after process start; retry import once.
        try:
            from groq import Groq as _Groq  # type: ignore

            Groq = _Groq
        except Exception:
            Groq = None
    if Groq is None:
        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            try:
                import requests

                prompt = _build_prompt(target, score, flags, related_contexts)
                payload = {
                    "model": MODEL_CANDIDATES[0],
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                }
                resp = requests.post(
                    GROQ_OPENAI_URL,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                text = (((data or {}).get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                text = str(text).strip()
                if text:
                    return text, {"mode": "groq_http", "model": MODEL_CANDIDATES[0]}
            except Exception as exc:
                return _fallback_report(target, score, flags, reason="groq_http_failed"), {
                    "mode": "fallback",
                    "reason": f"groq_http_failed: {str(exc)[:160]}",
                }

        return _fallback_report(target, score, flags, reason="missing groq package"), {
            "mode": "fallback",
            "reason": "missing_groq_dependency",
        }

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return _fallback_report(target, score, flags, reason="missing GROQ_API_KEY"), {
            "mode": "fallback",
            "reason": "missing_api_key",
        }

    prompt = _build_prompt(target, score, flags, related_contexts)
    client = Groq(api_key=api_key, timeout=8.0, max_retries=0)  # type: ignore[misc]

    def _request(model_name: str) -> str:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            timeout=8.0,
        )
        return (completion.choices[0].message.content or "").strip()

    last_error = "unknown"
    for model in MODEL_CANDIDATES:
        for attempt in range(1, 3):
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(_request, model)
                    text = future.result(timeout=10.0)
                if text:
                    return text, {
                        "mode": "groq",
                        "model": model,
                        "attempt": attempt,
                    }
                last_error = "empty_completion"
            except (FutureTimeoutError, Exception) as exc:
                last_error = str(exc)
                if attempt < 2:
                    time.sleep(0.8 * attempt)

    return _fallback_report(target, score, flags, reason="groq_request_failed"), {
        "mode": "fallback",
        "reason": last_error[:180],
    }


def generate_report(
    target: str,
    score: int,
    flags: list[str],
    related_contexts: list[str] | None = None,
) -> str:
    text, _ = generate_report_details(target, score, flags, related_contexts=related_contexts)
    return text
