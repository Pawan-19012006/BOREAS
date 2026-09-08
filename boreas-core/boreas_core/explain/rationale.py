"""Template natural-language rationale generation (BOREAS design doc §5.7).

Deliberately not an LLM call: a routing recommendation is a safety-relevant
statement, and a fixed template over structured fields is auditable,
reproducible, and fast. The template mirrors the worked example in the design
doc: "rerouted 12 nm south - 68% probability of ice concentration exceeding
70% over the next 72 hours, based on OSI-SAF drift trend and SIDDA vectors."
"""

from dataclasses import dataclass

from boreas_core.routing.astar import RouteResult
from boreas_core.uncertainty.ood import ConfidenceAssessment


@dataclass
class RouteRationale:
    headline: str
    confidence_statement: str
    contributing_factors: list[str]
    degraded_notice: str | None

    @property
    def full_text(self) -> str:
        parts = [self.headline, self.confidence_statement]
        if self.contributing_factors:
            parts.append("Contributing factors: " + "; ".join(self.contributing_factors) + ".")
        if self.degraded_notice:
            parts.append(self.degraded_notice)
        return " ".join(parts)


def _risk_band(max_risk: float) -> str:
    if max_risk >= 0.7:
        return "high"
    if max_risk >= 0.35:
        return "guarded"
    return "low"


def generate_drift_rationale(
    *,
    confidence: ConfidenceAssessment,
    top_factors: list[tuple[str, float]] | None = None,
) -> str:
    """Rationale for an iceberg drift forecast (as opposed to a route recommendation)."""
    parts = [
        f"Drift forecast confidence {confidence.confidence:.0%} "
        f"(ensemble spread {confidence.ensemble_std:.3f}, "
        f"distributional fit p={confidence.ood_p_value:.2f})."
    ]
    if top_factors:
        factor_text = ", ".join(
            f"{name} ({'+' if value >= 0 else ''}{value:.3f})" for name, value in top_factors[:3]
        )
        parts.append(f"Residual correction driven mainly by: {factor_text}.")
    if confidence.degraded:
        parts.append(
            "CONFIDENCE BELOW THRESHOLD: inputs look unlike the training distribution -- "
            "falling back to a conservative buffer rather than trusting this trajectory."
        )
    return " ".join(parts)


def generate_route_rationale(
    *,
    route: RouteResult,
    replanned: bool,
    replan_reason: str | None,
    confidence: ConfidenceAssessment,
    top_shap_factors: list[tuple[str, float]] | None = None,
    data_sources: list[str] | None = None,
) -> RouteRationale:
    band = _risk_band(route.max_risk_on_path)

    if replanned:
        headline = (
            f"Route re-planned ({replan_reason})." if replan_reason else "Route re-planned."
        )
    else:
        headline = "Holding current route -- no re-plan triggered."

    headline += (
        f" Peak along-route hazard is {band} ({route.max_risk_on_path:.0%}) over "
        f"{route.total_distance_km:.0f} km."
    )

    confidence_statement = (
        f"Confidence {confidence.confidence:.0%} "
        f"(ensemble spread {confidence.ensemble_std:.3f}, "
        f"distributional fit p={confidence.ood_p_value:.2f})."
    )

    factors = []
    if data_sources:
        factors.append("data: " + ", ".join(data_sources))
    if top_shap_factors:
        factors.extend(
            f"{name} ({'+' if value >= 0 else ''}{value:.3f})"
            for name, value in top_shap_factors[:3]
        )

    degraded_notice = None
    if confidence.degraded:
        degraded_notice = (
            "CONFIDENCE BELOW THRESHOLD: this recommendation has been superseded by a "
            "conservative deterministic buffer -- do not treat the route above as trusted."
        )

    return RouteRationale(
        headline=headline,
        confidence_statement=confidence_statement,
        contributing_factors=factors,
        degraded_notice=degraded_notice,
    )
