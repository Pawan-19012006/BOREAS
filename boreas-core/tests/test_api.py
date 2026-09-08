import pytest
from fastapi.testclient import TestClient

from boreas_core.api.server import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "OK"


def test_drift_forecast_endpoint():
    response = client.post(
        "/drift/forecast",
        json={
            "lon": 20.0,
            "lat": -66.0,
            "wind_east_ms": 8.0,
            "wind_north_ms": -2.0,
            "current_east_ms": 0.2,
            "current_north_ms": 0.1,
            "geometry": {"length_m": 4000, "width_m": 1500, "thickness_m": 250},
            "duration_hours": 48,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["track"]) > 1
    assert 0 <= body["confidence"] <= 1
    assert isinstance(body["rationale"], str) and body["rationale"]
    assert len(body["top_factors"]) == 3


def test_route_plan_endpoint_with_hazard():
    response = client.post(
        "/route/plan",
        json={
            "start_lon": -10,
            "start_lat": -70,
            "goal_lon": 10,
            "goal_lat": -68,
            "hazard_lon": [0],
            "hazard_lat": [-69],
            "hazard_radius_km": [80],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["options"]) >= 2  # both AI variants at minimum
    recommended = [o for o in body["options"] if o["recommended"]]
    assert len(recommended) == 1

    for option in body["options"]:
        assert len(option["path"]) >= 2
        assert option["total_distance_km"] > 0
        assert "rationale" in option
        assert len(option["legs"]) >= 1
        assert option["legs"][-1]["bearing_deg"] is None  # final arrival marker
        total_leg_distance = sum(leg["distance_km"] for leg in option["legs"])
        assert total_leg_distance == pytest.approx(option["total_distance_km"], rel=1e-6)


def test_route_plan_skips_polar_route_when_not_requested():
    response = client.post(
        "/route/plan",
        json={
            "start_lon": -10,
            "start_lat": -70,
            "goal_lon": 10,
            "goal_lat": -68,
            "include_polar_route": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert all(o["engine"] != "polar_route" for o in body["options"])
    # Deliberately skipped, not a failure -- no warning about it.
    assert not any("PolarRoute" in w for w in body["warnings"])


def test_ensemble_summary_endpoint_reports_availability():
    response = client.get("/forecast/ensemble-summary")
    assert response.status_code == 200
    body = response.json()
    assert "available" in body
    if body["available"]:
        assert body["n_members"] >= 2


def test_ensemble_grid_endpoint_reports_availability():
    response = client.get("/forecast/ensemble-grid")
    assert response.status_code == 200
    body = response.json()
    assert "available" in body
    if body["available"]:
        assert len(body["mean"]) == 32
        assert len(body["mean"][0]) == 32
        assert len(body["lat"]) == 32
        assert len(body["lon"]) == 32


def test_ensemble_grid_endpoint_rejects_out_of_range_index():
    response = client.get("/forecast/ensemble-grid?sample_index=9999")
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        assert response.json()["available"] is False


def test_edge_report_endpoint_reports_availability():
    response = client.get("/edge/report")
    assert response.status_code == 200
    body = response.json()
    assert "available" in body


def test_fusion_demo_endpoint():
    response = client.post(
        "/fusion/demo",
        json={
            "global_model_mean": 0.5,
            "global_model_variance": 0.09,
            "latitude_deg": -70,
            "month": 9,
            "true_concentration_for_synthetic_obs": 0.8,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fused_variance"] < body["global_model_variance"]
