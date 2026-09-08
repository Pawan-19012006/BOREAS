"""Process-lifetime singletons for the API: models trained once at startup.

Training the residual model and fitting the OOD detector both take well
under a second on the synthetic dataset (see data/synthetic_drift.py), so
there's no need for a separate offline training step or model registry yet
-- this can grow into one once real SIDDA/BYU-NIC data replaces the
synthetic generator.
"""

from dataclasses import dataclass
from pathlib import Path

from boreas_core.data.synthetic_drift import FEATURE_COLUMNS, generate_synthetic_drift_dataset
from boreas_core.explain.shap_explain import DriftExplainer
from boreas_core.physics.residual_model import ResidualDriftModel
from boreas_core.routing.policy import AdaptiveRouter
from boreas_core.uncertainty.ood import ConfidenceScorer, MahalanobisOODDetector

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts"
PPO_MODEL_PATH = ARTIFACTS_DIR / "ppo_router.zip"


@dataclass
class AppState:
    residual_model: ResidualDriftModel
    drift_explainer: DriftExplainer
    confidence_scorer: ConfidenceScorer
    router: AdaptiveRouter


_state: AppState | None = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = _build_state()
    return _state


def _build_state() -> AppState:
    dataset = generate_synthetic_drift_dataset(n_samples=4000, seed=0)

    residual_model = ResidualDriftModel(n_estimators=150)
    residual_model.fit(dataset, seed=0)
    drift_explainer = DriftExplainer(residual_model)

    ood_detector = MahalanobisOODDetector().fit(dataset.features[FEATURE_COLUMNS].to_numpy())
    confidence_scorer = ConfidenceScorer(
        ood_detector, ensemble_std_scale=0.1, degrade_threshold=0.15
    )

    router = AdaptiveRouter()
    if PPO_MODEL_PATH.exists():
        router.load_policy(PPO_MODEL_PATH)

    return AppState(
        residual_model=residual_model,
        drift_explainer=drift_explainer,
        confidence_scorer=confidence_scorer,
        router=router,
    )
