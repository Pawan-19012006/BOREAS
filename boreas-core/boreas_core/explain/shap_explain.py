"""SHAP feature attribution for the residual drift model (BOREAS design doc §5.7).

TreeExplainer is exact (not sampling-based) for gradient-boosted trees, so
attributions for `ResidualDriftModel` are cheap and deterministic -- this is
why the design doc pairs a GBM residual model with SHAP rather than reaching
for a post-hoc approximation like LIME.
"""

from dataclasses import dataclass

import numpy as np
import shap

from boreas_core.data.synthetic_drift import FEATURE_COLUMNS
from boreas_core.physics.residual_model import ResidualDriftModel


@dataclass
class DriftAttribution:
    component: str  # "east" or "north"
    base_value: float
    contributions: list[tuple[str, float]]  # sorted by |contribution|, descending


class DriftExplainer:
    def __init__(self, model: ResidualDriftModel) -> None:
        model._check_fitted()
        self.model = model
        self._explainer_east = shap.TreeExplainer(model.model_east_)
        self._explainer_north = shap.TreeExplainer(model.model_north_)

    def explain(self, feature_row: dict) -> list[DriftAttribution]:
        x = np.array([[feature_row[col] for col in FEATURE_COLUMNS]])
        results = []
        for component, explainer in (("east", self._explainer_east), ("north", self._explainer_north)):
            shap_values = explainer(x)
            contributions = sorted(
                zip(FEATURE_COLUMNS, shap_values.values[0].tolist(), strict=True),
                key=lambda kv: abs(kv[1]),
                reverse=True,
            )
            results.append(
                DriftAttribution(
                    component=component,
                    base_value=float(shap_values.base_values[0]),
                    contributions=contributions,
                )
            )
        return results

    def top_factors(self, feature_row: dict, k: int = 3) -> list[tuple[str, float]]:
        """Merged top-k factors across both velocity components, for the
        template rationale in explain/rationale.py.
        """
        attributions = self.explain(feature_row)
        merged: dict[str, float] = {}
        for attribution in attributions:
            for name, value in attribution.contributions:
                merged[name] = merged.get(name, 0.0) + abs(value)
        ranked = sorted(merged.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:k]
