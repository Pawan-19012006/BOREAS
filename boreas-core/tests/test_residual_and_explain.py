import numpy as np

from boreas_core.data.synthetic_drift import generate_synthetic_drift_dataset
from boreas_core.explain.rationale import generate_route_rationale
from boreas_core.explain.shap_explain import DriftExplainer
from boreas_core.physics.residual_model import ResidualDriftModel
from boreas_core.routing.astar import astar_route
from boreas_core.routing.grid import synthetic_southern_ocean_grid
from boreas_core.uncertainty.ood import ConfidenceScorer, MahalanobisOODDetector


def test_residual_model_beats_zero_baseline():
    dataset = generate_synthetic_drift_dataset(n_samples=1500, seed=1)
    model = ResidualDriftModel(n_estimators=100)
    metrics = model.fit(dataset, seed=1)

    assert metrics.mae_model_ms < metrics.mae_baseline_ms
    assert metrics.improvement_pct > 20.0  # the residual is structured, not pure noise


def test_shap_explainer_returns_ranked_factors():
    dataset = generate_synthetic_drift_dataset(n_samples=1500, seed=2)
    model = ResidualDriftModel(n_estimators=100)
    model.fit(dataset, seed=2)
    explainer = DriftExplainer(model)

    row = dataset.features.iloc[0].to_dict()
    top_factors = explainer.top_factors(row, k=3)

    assert len(top_factors) == 3
    names = [name for name, _ in top_factors]
    assert len(set(names)) == 3  # distinct features, sorted by |importance|
    importances = [value for _, value in top_factors]
    assert importances == sorted(importances, reverse=True)


def test_route_rationale_flags_degraded_confidence():
    grid = synthetic_southern_ocean_grid(seed=3)
    navigable = np.argwhere(grid.risk < 0.5)
    start, goal = tuple(navigable[0]), tuple(navigable[-1])
    route = astar_route(grid, start, goal)
    assert route is not None

    rng = np.random.default_rng(0)
    detector = MahalanobisOODDetector().fit(rng.normal(0, 1, size=(500, 2)))
    scorer = ConfidenceScorer(detector, ensemble_std_scale=0.05, degrade_threshold=0.9)
    degraded_assessment = scorer.assess(np.array([50.0, 50.0]), ensemble_std=0.01)

    rationale = generate_route_rationale(
        route=route,
        replanned=False,
        replan_reason=None,
        confidence=degraded_assessment,
    )
    assert degraded_assessment.degraded
    assert "CONFIDENCE BELOW THRESHOLD" in rationale.full_text
