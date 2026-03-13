from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from groq import Groq

MODEL_CANDIDATES = [
    "llama3-70b-8192",
    "llama-3.3-70b-versatile",
    "llama3-8b-8192",
]


def _fallback_report(target: str, score: int, flags: list[str], reason: str | None = None) -> str:
    reason_line = f" Reason: {reason}." if reason else ""
    if flags:
        return (
            f"Automated review for {target}: trust score is {score}/100. "
            f"Key risk signals detected: {', '.join(flags)}. "
            f"Proceed with enhanced verification before any transaction.{reason_line}"
        )
    return (
        f"Automated review for {target}: trust score is {score}/100 with no critical red flags. "
        f"Maintain standard due diligence and monitor for behavior changes.{reason_line}"
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
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return _fallback_report(target, score, flags, reason="missing GROQ_API_KEY"), {
            "mode": "fallback",
            "reason": "missing_api_key",
        }

    prompt = _build_prompt(target, score, flags, related_contexts)
    client = Groq(api_key=api_key, timeout=8.0, max_retries=0)

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
