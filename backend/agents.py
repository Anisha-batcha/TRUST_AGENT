from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

try:
    from backend.scraper import ScrapeError, collect_signals
except ModuleNotFoundError:
    from scraper import ScrapeError, collect_signals


@dataclass
class PipelineResult:
    metrics: dict[str, float]
    scored: dict[str, Any]
    pipeline: dict[str, Any]
    context_text: str


def run_agent_pipeline(
    target: str,
    category: str,
    score_fn: Callable[[str, str, dict[str, float]], dict[str, Any]],
    fallback_metrics_fn: Callable[[str, str], dict[str, float]],
) -> PipelineResult:
    collector_meta: dict[str, Any] = {
        "agent": "Data Collector",
        "mode": "fallback",
        "source_url": None,
        "notes": [],
    }
    context_text = ""

    try:
        scraped = collect_signals(target, category)
        metrics = scraped.metrics
        collector_meta["mode"] = scraped.mode
        collector_meta["source_url"] = scraped.source_url
        collector_meta["notes"].append("Live page signals extracted via Selenium")
        if scraped.mode == "http_fallback":
            collector_meta["notes"].append("Static HTTP fallback was used due to Selenium limitations")
        context_text = scraped.raw_text
    except ScrapeError as exc:
        metrics = fallback_metrics_fn(target, category)
        collector_meta["notes"].append(str(exc))
        collector_meta["notes"].append("Fallback synthetic metrics were used")
        context_text = f"Fallback-only analysis for {target} in category {category}"

    scored = score_fn(target, category, metrics)

    verifier_meta = {
        "agent": "Verifier",
        "checks": [
            "metric completeness",
            "red-flag deduplication",
            "confidence adjustment by data source",
        ],
        "actions": [],
    }

    if collector_meta["mode"] == "fallback":
        scored["data_state"] = "limited_data"
        scored["confidence_score"] = round(max(0.25, float(scored["confidence_score"]) - 0.15), 3)
        verifier_meta["actions"].append("Confidence reduced because scraping fallback was used")
    elif collector_meta["mode"] == "http_fallback":
        scored["confidence_score"] = round(max(0.25, float(scored["confidence_score"]) - 0.07), 3)
        verifier_meta["actions"].append("Confidence slightly reduced because static fallback mode was used")

    pipeline = {
        "collector": collector_meta,
        "scorer": {
            "agent": "Scorer",
            "model": "rules.v1",
            "signals_used": list(metrics.keys()),
        },
        "verifier": verifier_meta,
    }

    return PipelineResult(metrics=metrics, scored=scored, pipeline=pipeline, context_text=context_text)
