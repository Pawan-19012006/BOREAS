"""Unit tests for BOREAS Level 01 OBSERVE intelligence endpoints."""

import pytest
from fastapi.testclient import TestClient

from boreas_core.api.server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_observe_vessels_endpoint(client):
    response = client.get("/observe/vessels")
    assert response.status_code == 200
    data = response.json()

    assert "vessels" in data
    assert "total_count" in data
    assert "active_count" in data
    assert "provenance" in data
    assert "updated_at" in data

    assert data["total_count"] >= 8
    assert data["active_count"] >= 1
    assert "PROTOTYPE" in data["provenance"]

    # Verify vessel schema fields
    vessel = data["vessels"][0]
    required_fields = [
        "id",
        "name",
        "vessel_type",
        "ice_class",
        "latitude",
        "longitude",
        "heading_deg",
        "speed_kt",
        "destination",
        "eta",
        "status",
        "flag",
        "track_history",
        "source",
    ]
    for field in required_fields:
        assert field in vessel, f"Missing {field} in vessel"

    assert vessel["status"] in ["LIVE_AIS", "DEAD_RECKONING", "MOORED", "ICE_BOUND"]
    assert len(vessel["track_history"]) >= 2
    assert -90.0 <= vessel["latitude"] <= 90.0
    assert -180.0 <= vessel["longitude"] <= 180.0


def test_observe_icebergs_endpoint(client):
    response = client.get("/observe/icebergs")
    assert response.status_code == 200
    data = response.json()

    assert "icebergs" in data
    assert "total_count" in data
    assert "provenance" in data
    assert "updated_at" in data

    assert data["total_count"] >= 8

    # Verify specific famous and regional icebergs
    berg_ids = [b["id"] for b in data["icebergs"]]
    assert "A-23A" in berg_ids
    assert "D-28" in berg_ids
    assert "B-17" in berg_ids

    # Verify iceberg schema fields
    berg = data["icebergs"][0]
    required_fields = [
        "id",
        "name",
        "latitude",
        "longitude",
        "drift_speed_kt",
        "heading_deg",
        "length_m",
        "width_m",
        "thickness_m",
        "area_km2",
        "risk_level",
        "origin",
        "confidence",
        "track_history",
        "detection_source",
        "source",
    ]
    for field in required_fields:
        assert field in berg, f"Missing {field} in iceberg"

    assert berg["risk_level"] in ["low", "guarded", "high", "critical"]
    assert berg["detection_source"] in ["Sentinel-1", "Sentinel-2", "NIC Radar"]
    assert len(berg["track_history"]) >= 2
    assert 0.0 <= berg["confidence"] <= 1.0
