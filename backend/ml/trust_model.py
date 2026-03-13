from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

try:
    from sklearn.ensemble import RandomForestRegressor
except Exception:  # pragma: no cover - optional dependency fallback
    RandomForestRegressor = None


MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "trust_rf_model.json"


def _to_feature_vector(metrics: dict[str, float]) -> list[float]:
    return [
        float(metrics.get("engagement_rate", 0.0)),
        float(metrics.get("review_spike_ratio", 0.0)),
        float(metrics.get("profile_completeness", 0.0)),
        float(metrics.get("account_age_days", 0.0)),
        float(metrics.get("sentiment_score", 0.0)),
        float(metrics.get("follower_growth_consistency", 0.0)),
    ]


class TrustScoreModel:
    def __init__(self) -> None:
        self.model: Any = None
        self.last_signature = ""

    def _signature(self, rows: list[dict[str, Any]]) -> str:
        raw = json.dumps(rows, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _fit_if_needed(self, rows: list[dict[str, Any]]) -> str:
        if len(rows) < 10:
            return "insufficient_training_data"

        sig = self._signature(rows)
        if self.model is not None and sig == self.last_signature:
            return "model_cached"

        X = np.array([_to_feature_vector(r["metrics"]) for r in rows], dtype=float)
        y = np.array([float(r["trust_score"]) for r in rows], dtype=float)

        if RandomForestRegressor is None:
            self.model = None
            self.last_signature = sig
            return "sklearn_unavailable"

        model = RandomForestRegressor(
            n_estimators=120,
            max_depth=8,
            min_samples_split=2,
            random_state=42,
        )
        model.fit(X, y)
        self.model = model
        self.last_signature = sig
        return "model_trained"

    def predict(
        self,
        metrics: dict[str, float],
        rule_score: int,
        training_rows: list[dict[str, Any]],
    ) -> tuple[int, dict[str, Any]]:
        status = self._fit_if_needed(training_rows)
        features = np.array([_to_feature_vector(metrics)], dtype=float)

        if self.model is not None:
            pred = float(self.model.predict(features)[0])
            ml_score = int(max(10, min(99, round(pred))))
            return ml_score, {"status": status, "strategy": "random_forest"}

        # Deterministic fallback if sklearn/model is unavailable.
        engagement = float(metrics.get("engagement_rate", 0.0))
        spike = float(metrics.get("review_spike_ratio", 0.0))
        sentiment = float(metrics.get("sentiment_score", 0.5))
        profile = float(metrics.get("profile_completeness", 0.6))
        age = float(metrics.get("account_age_days", 180.0))
        age_bonus = min(10.0, np.log1p(max(age, 1.0)) * 1.2)
        heuristic = rule_score + (engagement * 120) - (spike * 20) + ((sentiment - 0.5) * 18) + ((profile - 0.5) * 12) + age_bonus - 8
        ml_score = int(max(10, min(99, round(heuristic))))
        return ml_score, {"status": status, "strategy": "heuristic_fallback"}


trust_model = TrustScoreModel()
