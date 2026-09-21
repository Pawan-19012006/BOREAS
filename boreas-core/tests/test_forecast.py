"""Unit tests for the BOREAS Prediction Subsystem.

Tests iceberg kinematic drift, growing uncertainty envelopes, spatial
sea-ice evolution, atmospheric forcing, and unified future state composition.
"""

import pytest
from fastapi.testclient import TestClient

from boreas_core.api.server import app
from boreas_core.forecast import (
    IcebergTrajectoryEngine,
    SeaIceForecastEngine,
    EnvironmentalForecastEngine,
    get_future_state,
)
from boreas_core.observe.service import get_observed_icebergs


@pytest.fixture
def client():
    return TestClient(app)


def test_iceberg_trajectory_engine_uncertainty_growth():
    engine = IcebergTrajectoryEngine()
    icebergs = get_observed_icebergs().icebergs
    berg = icebergs[0]

    forecast = engine.forecast_iceberg(berg, horizons=[12, 24, 48, 72, 96, 120])
    assert len(forecast.forecast_points) == 6

    # Verify monotonic growth of uncertainty radius
    uncertainties = [pt.uncertainty_radius_km for pt in forecast.forecast_points]
    for i in range(len(uncertainties) - 1):
        assert uncertainties[i] < uncertainties[i + 1], (
            f"Uncertainty at h={forecast.forecast_points[i].horizon_hours} ({uncertainties[i]}km) "
            f"should be less than at h={forecast.forecast_points[i+1].horizon_hours} ({uncertainties[i+1]}km)"
        )

    # Verify confidence decay
    confidences = [pt.confidence for pt in forecast.forecast_points]
    for i in range(len(confidences) - 1):
        assert confidences[i] >= confidences[i + 1]

    # Verify spatial coordinates validity
    for pt in forecast.forecast_points:
        assert -90.0 <= pt.latitude <= 90.0
        assert -180.0 <= pt.longitude <= 180.0
        assert pt.drift_speed_kt > 0


def test_sea_ice_forecast_engine_determinism():
    engine = SeaIceForecastEngine()
    res1 = engine.predict_grid(horizon_hours=48)
    res2 = engine.predict_grid(horizon_hours=48)

    assert res1.horizon_hours == 48
    assert len(res1.grid_lat) == 32
    assert len(res1.grid_lon) == 32
    assert len(res1.sic_values) == 32
    assert len(res1.sic_values[0]) == 32

    # Determinism check
    assert res1.sic_values == res2.sic_values
    assert res1.mean_concentration_pct == res2.mean_concentration_pct

    # Evolution across horizons
    res_12 = engine.predict_grid(horizon_hours=12)
    res_120 = engine.predict_grid(horizon_hours=120)
    assert res_12.confidence > res_120.confidence


def test_environmental_forecast_engine():
    engine = EnvironmentalForecastEngine()
    env_res = engine.get_full_forecast()

    assert env_res.current.horizon_hours == 0
    assert len(env_res.forecasts) == 6

    for pt in env_res.forecasts:
        assert pt.wind_speed_kt > 0
        assert 0.0 <= pt.wind_direction_deg <= 360.0
        assert pt.wave_height_m > 0
        assert pt.pressure_hpa > 900
        assert pt.visibility_nm > 0


def test_future_state_composition():
    state_48 = get_future_state(horizon_hours=48)

    assert state_48.horizon_hours == 48
    assert len(state_48.vessels) >= 8
    assert len(state_48.icebergs) >= 8
    assert state_48.sea_ice.horizon_hours == 48
    assert state_48.environment.horizon_hours == 48
    assert 0.0 <= state_48.overall_confidence <= 1.0
    assert "vessels" in state_48.provenance
    assert "icebergs" in state_48.provenance


def test_forecast_api_endpoints(client):
    # 1. /forecast/icebergs
    res_bergs = client.get("/forecast/icebergs?horizon_hours=72")
    assert res_bergs.status_code == 200
    data_bergs = res_bergs.json()
    assert len(data_bergs) >= 8
    assert "forecast_points" in data_bergs[0]

    # 2. /forecast/sea-ice
    res_ice = client.get("/forecast/sea-ice?horizon_hours=48")
    assert res_ice.status_code == 200
    data_ice = res_ice.json()
    assert data_ice["horizon_hours"] == 48
    assert len(data_ice["sic_values"]) == 32

    # 3. /forecast/environment
    res_env = client.get("/forecast/environment")
    assert res_env.status_code == 200
    data_env = res_env.json()
    assert len(data_env["forecasts"]) == 6

    # 4. /forecast/state
    res_state = client.get("/forecast/state?horizon_hours=72")
    assert res_state.status_code == 200
    data_state = res_state.json()
    assert data_state["horizon_hours"] == 72
    assert len(data_state["vessels"]) >= 8
    assert len(data_state["icebergs"]) >= 8
