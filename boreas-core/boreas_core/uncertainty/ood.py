"""Out-of-distribution detection via Mahalanobis distance (BOREAS design doc §5.4).

Mahalanobis distance is the natural first-principles choice here: under a
(locally) multivariate-Gaussian assumption for the training feature
distribution, its square is chi-square distributed with `D` degrees of
freedom, which gives a calibrated p-value for "how surprising is this input"
rather than an arbitrary distance threshold.
"""

from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass
class MahalanobisOODDetector:
    """Fits a Gaussian to reference (training-distribution) features."""

    regularization: float = 1e-6
    mean_: np.ndarray | None = None
    inv_cov_: np.ndarray | None = None
    n_features_: int = 0

    def fit(self, reference_features: np.ndarray) -> "MahalanobisOODDetector":
        x = np.asarray(reference_features, dtype=float)
        if x.ndim != 2:
            raise ValueError("reference_features must be 2D: (n_samples, n_features)")
        self.mean_ = x.mean(axis=0)
        cov = np.cov(x, rowvar=False)
        cov = np.atleast_2d(cov)
        self.n_features_ = cov.shape[0]
        cov_reg = cov + self.regularization * np.eye(self.n_features_)
        self.inv_cov_ = np.linalg.pinv(cov_reg)
        return self

    def _check_fitted(self) -> None:
        if self.mean_ is None or self.inv_cov_ is None:
            raise RuntimeError("MahalanobisOODDetector must be fit() before use.")

    def distance(self, x: np.ndarray) -> float:
        """Mahalanobis distance of a single feature vector from the reference distribution."""
        self._check_fitted()
        delta = np.asarray(x, dtype=float) - self.mean_
        return float(np.sqrt(delta @ self.inv_cov_ @ delta))

    def p_value(self, x: np.ndarray) -> float:
        """P(a reference-distribution sample is at least this extreme).

        Low p-value => the input looks unlike anything the model was trained
        on => predictions here should not be trusted at face value.
        """
        d2 = self.distance(x) ** 2
        return float(stats.chi2.sf(d2, df=self.n_features_))


@dataclass
class ConfidenceAssessment:
    ensemble_std: float
    ood_distance: float
    ood_p_value: float
    confidence: float
    degraded: bool


class ConfidenceScorer:
    """Fuses ensemble spread (epistemic) with OOD p-value (distributional) into
    the single self-declared confidence score described in BOREAS §5.4, and
    decides whether the routing engine should fall back to a conservative
    deterministic rule instead of trusting the ML output.
    """

    def __init__(
        self,
        ood_detector: MahalanobisOODDetector,
        *,
        ensemble_std_scale: float,
        degrade_threshold: float = 0.4,
    ) -> None:
        self.ood_detector = ood_detector
        self.ensemble_std_scale = ensemble_std_scale
        self.degrade_threshold = degrade_threshold

    def assess(self, features: np.ndarray, ensemble_std: float) -> ConfidenceAssessment:
        p_value = self.ood_detector.p_value(features)
        distance = self.ood_detector.distance(features)

        # Epistemic term: ensemble agreement, mapped to (0, 1] via a smooth decay.
        epistemic_confidence = 1.0 / (1.0 + ensemble_std / self.ensemble_std_scale)
        # Distributional term: the OOD p-value is already a probability in [0, 1].
        distributional_confidence = p_value

        confidence = float(epistemic_confidence * distributional_confidence)
        degraded = confidence < self.degrade_threshold

        return ConfidenceAssessment(
            ensemble_std=float(ensemble_std),
            ood_distance=distance,
            ood_p_value=p_value,
            confidence=confidence,
            degraded=degraded,
        )
