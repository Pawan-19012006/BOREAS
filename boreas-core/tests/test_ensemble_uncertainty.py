import numpy as np

from boreas_core.uncertainty.ensemble import load_ensemble_forecast


def test_load_ensemble_forecast_computes_mean_and_std(tmp_path):
    rng = np.random.default_rng(0)
    n, t, c, h, w = 5, 2, 1, 4, 4
    n_members = 4

    inputs = rng.random((n, 3, c, h, w))
    targets = rng.random((n, t, c, h, w))
    # Members agree closely on some samples, disagree wildly on others --
    # a real ensemble should reflect that as spatially-varying uncertainty.
    base = rng.random((n, t, c, h, w))
    member_predictions = np.stack(
        [base + rng.normal(0, 0.01, base.shape) for _ in range(n_members)]
    )
    member_predictions[:, -1] = np.stack(
        [base[-1] + rng.normal(0, 0.5, base[-1].shape) for _ in range(n_members)]
    )

    npz_path = tmp_path / "ensemble_export.npz"
    np.savez(
        npz_path,
        inputs=inputs,
        targets=targets,
        member_predictions=member_predictions,
        ensemble_mean=member_predictions.mean(axis=0),
        ensemble_std=member_predictions.std(axis=0),
    )

    forecast = load_ensemble_forecast(npz_path)
    assert forecast.n_members == n_members
    # The deliberately-noisy last sample should show far higher spread than the rest.
    assert forecast.std[-1].mean() > 5 * forecast.std[:-1].mean()


def test_confidence_map_decreases_with_spread(tmp_path):
    from boreas_core.uncertainty.ensemble import EnsembleForecast

    shape = (2, 1, 1, 3, 3)
    low_std = np.full(shape, 0.01)
    high_std = np.full(shape, 2.0)

    forecast_low = EnsembleForecast(
        inputs=np.zeros(shape), targets=np.zeros(shape),
        member_predictions=np.zeros((3, *shape)), mean=np.zeros(shape), std=low_std,
    )
    forecast_high = EnsembleForecast(
        inputs=np.zeros(shape), targets=np.zeros(shape),
        member_predictions=np.zeros((3, *shape)), mean=np.zeros(shape), std=high_std,
    )

    assert forecast_low.confidence_map(std_scale=0.1).mean() > forecast_high.confidence_map(
        std_scale=0.1
    ).mean()
