"""Indian satellite/climatology data fusion (BOREAS design doc §5.5).

STATUS: interface + synthetic stand-in. The design doc specifies four real
NCPOR/ISRO products, distributed via MOSDAC and each requiring a registered
data-access agreement this environment doesn't have:
  - SIOP: Sea Ice Occurrence Probability climatology (1978-2012, NSIDC-derived)
  - SCATSAT-1: daily 2.25 km Antarctic ice maps (Rajak et al. 2021)
  - SARAL/AltiKa: ice-extent record, Apr 2013-Dec 2024 (Joshi et al. 2026)
  - SIDDA: Sentinel-1 SAR ice-drift tracker (also used in physics/residual_model.py)

The fusion *pattern* below -- "Indian data = prior/correction, global model =
base forecast" -- is the real content of this module: a standard Bayesian
conjugate-Gaussian update, not a novel algorithm. `SyntheticSIOPClimatology`
and `SyntheticRegionalObservation` generate statistically-representative
stand-ins (a real Antarctic seasonal cycle, a spatial gradient toward the
continent, calibrated noise) purely so the fusion math has something to
combine today. Swapping in real MOSDAC feeds means replacing these two
classes' data source with a loader against the same (mean, variance)
interface -- `BayesianFusion.fuse` does not change.
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class GaussianEstimate:
    """A concentration estimate with its variance -- the common currency both
    the global forecast and the Indian correction products are expressed in
    so they can be fused by precision-weighting.
    """

    mean: float  # ice concentration fraction, [0, 1]
    variance: float


def fuse_gaussian(prior: GaussianEstimate, observation: GaussianEstimate) -> GaussianEstimate:
    """Standard Gaussian conjugate update (inverse-variance weighting).

    This is the textbook-optimal way to combine two independent unbiased
    estimates of the same quantity, weighting each by the inverse of its own
    variance -- precisely the "prior + correction" pattern in BOREAS design doc
    §5.5, made precise.
    """
    if prior.variance <= 0 or observation.variance <= 0:
        raise ValueError("variances must be positive")
    prior_precision = 1.0 / prior.variance
    obs_precision = 1.0 / observation.variance
    posterior_precision = prior_precision + obs_precision
    posterior_mean = (
        prior.mean * prior_precision + observation.mean * obs_precision
    ) / posterior_precision
    return GaussianEstimate(mean=float(posterior_mean), variance=float(1.0 / posterior_precision))


class SyntheticSIOPClimatology:
    """Stand-in for the SIOP (Sea Ice Occurrence Probability) climatology:
    a monthly, latitude-dependent seasonal prior with realistic Antarctic
    phase (maximum extent ~September, minimum ~February).
    """

    def __init__(self, *, climatology_variance: float = 0.04) -> None:
        self.climatology_variance = climatology_variance

    def prior(self, *, latitude_deg: float, month: int) -> GaussianEstimate:
        if not 1 <= month <= 12:
            raise ValueError("month must be in [1, 12]")
        # Antarctic sea-ice extent peaks around September (month 9), consistent
        # with the real seasonal cycle SIOP is built from.
        phase = 2 * np.pi * (month - 9) / 12
        seasonal_amplitude = 0.5 * (1 + np.cos(phase))
        # More concentration expected further south / closer to the continent.
        latitude_factor = np.clip((-latitude_deg - 55) / 25, 0, 1)
        mean = float(np.clip(0.15 + 0.75 * seasonal_amplitude * latitude_factor, 0, 1))
        return GaussianEstimate(mean=mean, variance=self.climatology_variance)


class SyntheticRegionalObservation:
    """Stand-in for the SCATSAT-1 / SARAL-AltiKa regional correction layer:
    a higher-resolution, lower-variance observation of the same quantity the
    global model / SIOP prior estimates, sampled around a "true" synthetic
    field so the fusion demonstrably tightens the estimate.
    """

    def __init__(self, *, observation_variance: float = 0.01, seed: int = 0) -> None:
        self.observation_variance = observation_variance
        self._rng = np.random.default_rng(seed)

    def observe(self, true_concentration: float) -> GaussianEstimate:
        noisy_mean = float(
            np.clip(
                true_concentration + self._rng.normal(0, np.sqrt(self.observation_variance)),
                0,
                1,
            )
        )
        return GaussianEstimate(mean=noisy_mean, variance=self.observation_variance)


@dataclass
class FusionResult:
    global_model_estimate: GaussianEstimate
    indian_prior: GaussianEstimate
    indian_correction: GaussianEstimate
    fused: GaussianEstimate


class IndianDataFusionLayer:
    """Fuses (global model forecast) -> (SIOP prior) -> (regional correction)
    in sequence, each step narrowing the variance -- the concrete realisation
    of "Indian data = prior/correction, global model = base forecast."
    """

    def __init__(
        self,
        climatology: SyntheticSIOPClimatology | None = None,
        regional_observation: SyntheticRegionalObservation | None = None,
    ) -> None:
        self.climatology = climatology or SyntheticSIOPClimatology()
        self.regional_observation = regional_observation or SyntheticRegionalObservation()

    def fuse(
        self,
        *,
        global_model_mean: float,
        global_model_variance: float,
        latitude_deg: float,
        month: int,
        true_concentration_for_synthetic_obs: float,
    ) -> FusionResult:
        global_estimate = GaussianEstimate(global_model_mean, global_model_variance)
        prior = self.climatology.prior(latitude_deg=latitude_deg, month=month)
        step1 = fuse_gaussian(global_estimate, prior)

        correction = self.regional_observation.observe(true_concentration_for_synthetic_obs)
        fused = fuse_gaussian(step1, correction)

        return FusionResult(
            global_model_estimate=global_estimate,
            indian_prior=prior,
            indian_correction=correction,
            fused=fused,
        )
