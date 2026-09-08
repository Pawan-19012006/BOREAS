import numpy as np

from boreas_core.uncertainty.fallback import buffer_contains_point, conservative_buffer_forecast
from boreas_core.uncertainty.ood import ConfidenceScorer, MahalanobisOODDetector


def test_in_distribution_point_has_small_distance_and_high_pvalue():
    rng = np.random.default_rng(0)
    reference = rng.normal(0, 1, size=(2000, 3))
    detector = MahalanobisOODDetector().fit(reference)

    typical_point = np.array([0.1, -0.2, 0.05])
    assert detector.distance(typical_point) < 2.0
    assert detector.p_value(typical_point) > 0.1


def test_out_of_distribution_point_has_large_distance_and_low_pvalue():
    rng = np.random.default_rng(0)
    reference = rng.normal(0, 1, size=(2000, 3))
    detector = MahalanobisOODDetector().fit(reference)

    extreme_point = np.array([20.0, -18.0, 25.0])
    assert detector.distance(extreme_point) > 10.0
    assert detector.p_value(extreme_point) < 1e-6


def test_confidence_scorer_degrades_on_ood_input():
    rng = np.random.default_rng(0)
    reference = rng.normal(0, 1, size=(2000, 3))
    detector = MahalanobisOODDetector().fit(reference)
    scorer = ConfidenceScorer(detector, ensemble_std_scale=0.1, degrade_threshold=0.4)

    in_dist = scorer.assess(np.array([0.0, 0.0, 0.0]), ensemble_std=0.02)
    ood = scorer.assess(np.array([30.0, -30.0, 30.0]), ensemble_std=0.02)

    assert not in_dist.degraded
    assert ood.degraded
    assert ood.confidence < in_dist.confidence


def test_confidence_scorer_degrades_on_wide_ensemble_spread():
    rng = np.random.default_rng(0)
    reference = rng.normal(0, 1, size=(2000, 3))
    detector = MahalanobisOODDetector().fit(reference)
    scorer = ConfidenceScorer(detector, ensemble_std_scale=0.05, degrade_threshold=0.4)

    tight = scorer.assess(np.array([0.0, 0.0, 0.0]), ensemble_std=0.01)
    wide = scorer.assess(np.array([0.0, 0.0, 0.0]), ensemble_std=5.0)

    assert not tight.degraded
    assert wide.degraded


def test_conservative_buffer_grows_with_elapsed_time():
    early = conservative_buffer_forecast(last_lon=0, last_lat=-65, hours_since_observation=1)
    late = conservative_buffer_forecast(last_lon=0, last_lat=-65, hours_since_observation=24)
    assert late.radius_km > early.radius_km
    assert buffer_contains_point(early, 0, -65)


def test_conservative_buffer_excludes_far_point():
    buf = conservative_buffer_forecast(last_lon=0, last_lat=-65, hours_since_observation=1)
    assert not buffer_contains_point(buf, 50, -65)
