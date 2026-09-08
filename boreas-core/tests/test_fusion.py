import numpy as np

from boreas_core.fusion.indian_data import (
    GaussianEstimate,
    IndianDataFusionLayer,
    SyntheticRegionalObservation,
    SyntheticSIOPClimatology,
    fuse_gaussian,
)


def test_fuse_gaussian_reduces_variance_below_both_inputs():
    a = GaussianEstimate(mean=0.5, variance=0.04)
    b = GaussianEstimate(mean=0.6, variance=0.01)
    fused = fuse_gaussian(a, b)
    assert fused.variance < a.variance
    assert fused.variance < b.variance


def test_fuse_gaussian_weights_toward_lower_variance_input():
    a = GaussianEstimate(mean=0.2, variance=1.0)  # very uncertain
    b = GaussianEstimate(mean=0.8, variance=0.001)  # very confident
    fused = fuse_gaussian(a, b)
    assert abs(fused.mean - b.mean) < abs(fused.mean - a.mean)


def test_siop_climatology_peaks_in_austral_winter_near_continent():
    clim = SyntheticSIOPClimatology()
    winter = clim.prior(latitude_deg=-70, month=9)
    summer = clim.prior(latitude_deg=-70, month=2)
    assert winter.mean > summer.mean

    near_continent = clim.prior(latitude_deg=-75, month=9)
    open_ocean = clim.prior(latitude_deg=-56, month=9)
    assert near_continent.mean > open_ocean.mean


def test_regional_observation_centers_on_truth():
    rng_obs = SyntheticRegionalObservation(observation_variance=0.0001, seed=0)
    samples = [rng_obs.observe(0.7).mean for _ in range(200)]
    assert abs(np.mean(samples) - 0.7) < 0.02


def test_fusion_layer_narrows_variance_monotonically():
    layer = IndianDataFusionLayer()
    result = layer.fuse(
        global_model_mean=0.5,
        global_model_variance=0.09,
        latitude_deg=-70,
        month=9,
        true_concentration_for_synthetic_obs=0.75,
    )
    assert result.fused.variance < result.global_model_estimate.variance
    assert result.fused.variance < result.indian_prior.variance
    assert result.fused.variance < result.indian_correction.variance
