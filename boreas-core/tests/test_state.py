"""Unit tests for BOREAS Unified Current State X(t)."""

import pytest
from fastapi.testclient import TestClient

from boreas_core.api.server import app
from boreas_core.state import get_current_state


@pytest.fixture
def client():
    return TestClient(app)


def test_get_current_state_direct():
    state = get_current_state()

    assert state.timestamp is not None
    assert len(state.vessels) >= 8
    assert len(state.icebergs) >= 8

    # Sea ice checks
    assert 0.0 <= state.sea_ice.mean_concentration_pct <= 100.0
    assert 0.0 <= state.sea_ice.max_concentration_pct <= 100.0
    assert "OSI-SAF" in state.sea_ice.provenance or "DERIVED" in state.sea_ice.provenance

    # Weather checks
    assert state.weather.wind_speed_kt > 0
    assert 0.0 <= state.weather.wind_direction_deg <= 360.0
    assert state.weather.wave_height_m >= 0.0

    # Quality & Provenance
    assert 0.0 <= state.quality.overall_quality <= 1.0
    assert state.quality.satellite_provenance == "REAL"
    assert state.quality.ais_provenance == "PROTOTYPE"
    assert state.quality.iceberg_provenance == "DERIVED"

    assert "vessels" in state.provenance
    assert "icebergs" in state.provenance
    assert "satellites" in state.provenance


def test_state_current_api_endpoint(client):
    response = client.get("/state/current")
    assert response.status_code == 200
    data = response.json()

    assert "timestamp" in data
    assert "vessels" in data
    assert "icebergs" in data
    assert "sea_ice" in data
    assert "ocean" in data
    assert "weather" in data
    assert "bathymetry" in data
    assert "quality" in data
    assert "provenance" in data

    # Verify vessels and icebergs are populated
    assert len(data["vessels"]) >= 8
    assert len(data["icebergs"]) >= 8
    assert data["quality"]["overall_quality"] > 0
