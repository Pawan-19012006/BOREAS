"""Tests for POST /mission/plan (Cape Town -> Bharati/Maitri route alternatives)."""

import dataclasses
from functools import lru_cache

import numpy as np
import pytest
from fastapi.testclient import TestClient

from boreas_core.api.server import app
from boreas_core.mission import MissionPlanRequest, plan_mission
from boreas_core.mission.config import (
    DEFAULT_ICE_THRESHOLDS,
    DOMAIN_LAT_RANGE,
    DOMAIN_LON_RANGE,
    MISSIONS,
    profile_for_ice_class,
)
from boreas_core.mission.fields import BergHazard, build_snapshot, domain_axes, haversine_km_array, in_domain, land_mask
from boreas_core.mission.planner import MIN_SEPARATION_KM, _evaluate_route, _separation_km
from boreas_core.mission.fields import FieldModel

client = TestClient(app)
MISSION_IDS = list(MISSIONS)


def _post(**body):
    return client.post("/mission/plan", json=body)


@lru_cache(maxsize=None)
def _plan(mission_id: str, horizon: int = 0, weights: tuple | None = None):
    kw = {} if weights is None else {"weights": {"risk": weights[0], "fuel": weights[1], "eta": weights[2]}}
    return plan_mission(MissionPlanRequest(mission_id=mission_id, horizon_hours=horizon, **kw))


def _routes(resp):
    return {r.route_id: r for r in resp.routes}


def _clean_snapshot(horizon: int = 0):
    """Open water, no icebergs -- a controlled baseline for injection tests."""
    snap = build_snapshot(horizon)
    return dataclasses.replace(snap, sic=np.zeros_like(snap.sic), icebergs=[])


def _wall_snapshot(clean, *, lat=(-62.0, -52.0), lon=(-5.0, 40.0), value=0.95):
    sic = clean.sic.copy()
    la, lo = np.meshgrid(clean.sea_ice_lat, clean.sea_ice_lon, indexing="ij")
    sic[(la >= lat[0]) & (la <= lat[1]) & (lo >= lon[0]) & (lo <= lon[1])] = value
    return dataclasses.replace(clean, sic=sic)


def _fm(snapshot, mission_id="CAPE_TOWN_TO_MAITRI", vessel_ice_class="Arc5 / UL"):
    return FieldModel(snapshot, profile_for_ice_class(vessel_ice_class), DEFAULT_ICE_THRESHOLDS)


# ------------------------------------------------------------------ domain ---

def test_cape_town_and_stations_inside_domain():
    for m in MISSIONS.values():
        assert in_domain(*m.origin), m.origin
        assert in_domain(*m.destination), m.destination
    lons, lats = domain_axes()
    assert lats.max() >= MISSIONS["CAPE_TOWN_TO_MAITRI"].origin[1]  # -33.9 is not clamped away
    assert (lons.min(), lons.max()) == DOMAIN_LON_RANGE
    assert lats.min() == DOMAIN_LAT_RANGE[0]


@pytest.mark.parametrize("mission_id", MISSION_IDS)
def test_routes_start_at_cape_town_and_end_at_station(mission_id):
    resp, m = _plan(mission_id), MISSIONS[mission_id]
    assert resp.domain.origin_snap_km < 60 and resp.domain.destination_snap_km < 60
    lons, lats = domain_axes()
    land = land_mask(lons, lats)
    for r in resp.routes:
        assert r.coordinates[0] == list(m.origin)
        assert r.coordinates[-1] == list(m.destination)
        # first search vertex is within one coarse cell of Cape Town (no latitude clamping)
        assert abs(r.coordinates[1][1] - m.origin[1]) < 1.5
        for lon, lat in r.coordinates[1:-1]:
            assert in_domain(lon, lat)
            row, col = int(round(lat - lats[0])), int(round(lon - lons[0]))
            assert not land[row, col]


# ------------------------------------------------------------------ routes ---

@pytest.mark.parametrize("mission_id", MISSION_IDS)
def test_three_distinct_valid_routes(mission_id):
    resp = _plan(mission_id)
    assert [r.route_id for r in resp.routes] == ["recommended", "low_risk", "fast_fuel"]
    assert [r.label for r in resp.routes] == ["RECOMMENDED", "LOW-RISK ALTERNATIVE", "FASTEST / FUEL-ORIENTED"]
    for a in range(3):
        for b in range(a + 1, 3):
            assert resp.routes[a].coordinates != resp.routes[b].coordinates
            assert _separation_km(resp.routes[a].coordinates, resp.routes[b].coordinates) >= MIN_SEPARATION_KM
    for r in resp.routes:
        assert len(r.coordinates) > 5
        assert r.distance_km > 3000 and r.eta_hours > 100 and r.estimated_fuel.tonnes > 0
        assert r.estimated_fuel.label == "PROTOTYPE ESTIMATE"
        assert 0.0 <= r.risk_score <= 1.0 and 0.0 <= r.confidence <= 1.0
        assert r.generation and r.provenance["passability"].startswith("PROTOTYPE PASSABILITY MODEL")


def test_missions_differ_in_destination_and_geometry():
    bharati, maitri = _plan("CAPE_TOWN_TO_BHARATI"), _plan("CAPE_TOWN_TO_MAITRI")
    assert bharati.routes[0].coordinates[-1] != maitri.routes[0].coordinates[-1]
    assert bharati.routes[0].distance_km > maitri.routes[0].distance_km  # 76E is farther than 12E


def test_weights_change_route_characteristics():
    risk_heavy = _routes(_plan("CAPE_TOWN_TO_BHARATI", 0, (0.9, 0.05, 0.05)))["recommended"]
    eta_heavy = _routes(_plan("CAPE_TOWN_TO_BHARATI", 0, (0.05, 0.475, 0.475)))["recommended"]
    assert risk_heavy.coordinates != eta_heavy.coordinates
    assert risk_heavy.risk_score < eta_heavy.risk_score
    assert eta_heavy.eta_hours < risk_heavy.eta_hours
    assert eta_heavy.estimated_fuel.tonnes < risk_heavy.estimated_fuel.tonnes


# ----------------------------------------------------- hazards affect routing ---

def test_sea_ice_affects_routing():
    clean = _clean_snapshot()
    walled = _wall_snapshot(clean)
    req = MissionPlanRequest(mission_id="CAPE_TOWN_TO_MAITRI")
    rec_clean = _routes(plan_mission(req, snapshot=clean))["recommended"]
    rec_wall = _routes(plan_mission(req, snapshot=walled))["recommended"]
    assert _separation_km(rec_clean.coordinates, rec_wall.coordinates) > MIN_SEPARATION_KM
    # what the clean route would have suffered under the same ice wall
    m = MISSIONS["CAPE_TOWN_TO_MAITRI"]
    naive = _evaluate_route(rec_clean.coordinates, _fm(walled), "Arc5 / UL", DEFAULT_ICE_THRESHOLDS, walled)
    assert naive["sea_ice"].impassable_pct > 15.0  # the wall really is on the straight route
    assert rec_wall.sea_ice_exposure.mean_sic_pct < naive["sea_ice"].mean_sic_pct
    assert rec_wall.distance_km > rec_clean.distance_km  # the price of avoiding it
    assert m.destination == tuple(rec_wall.coordinates[-1])


def test_iceberg_forecast_affects_routing():
    clean = _clean_snapshot()
    req = MissionPlanRequest(mission_id="CAPE_TOWN_TO_MAITRI")
    rec_clean = _routes(plan_mission(req, snapshot=clean))["recommended"]
    mid_lon, mid_lat = rec_clean.coordinates[len(rec_clean.coordinates) // 2]
    berg = BergHazard(
        id="TEST-1", name="Injected", lon=mid_lon, lat=mid_lat, risk_level="critical",
        physical_radius_km=25.0, uncertainty_radius_km=20.0, confidence=0.9,
    )
    with_berg = dataclasses.replace(clean, icebergs=[berg])
    rec_berg = _routes(plan_mission(req, snapshot=with_berg))["recommended"]

    naive = _evaluate_route(rec_clean.coordinates, _fm(with_berg), "Arc5 / UL", DEFAULT_ICE_THRESHOLDS, with_berg)
    assert naive["bergs"].intersecting_count + naive["bergs"].potential_count == 1  # straight route hits it
    assert rec_berg.iceberg_exposure.intersecting_count == 0
    assert rec_berg.iceberg_exposure.potential_count == 0
    assert rec_berg.coordinates != rec_clean.coordinates
    assert rec_berg.iceberg_exposure.max_risk < naive["bergs"].max_risk


def test_iceberg_positions_and_uncertainty_come_from_forecast_service_per_horizon():
    now, later = build_snapshot(0), build_snapshot(120)
    by_id = lambda s: {b.id: b for b in s.icebergs}  # noqa: E731
    assert len(now.icebergs) == 10
    moved = [b for b in later.icebergs if (b.lon, b.lat) != (by_id(now)[b.id].lon, by_id(now)[b.id].lat)]
    assert len(moved) == 10
    assert all(b.uncertainty_radius_km > by_id(now)[b.id].uncertainty_radius_km for b in later.icebergs)


@pytest.mark.parametrize("mission_id", MISSION_IDS)
def test_horizon_affects_evaluation(mission_id):
    a, b, c = (_routes(_plan(mission_id, h))["recommended"] for h in (0, 48, 120))
    fingerprints = {
        (r.weather_exposure.max_wave_m, r.sea_ice_exposure.mean_sic_pct, r.risk_score, r.eta_hours)
        for r in (a, b, c)
    }
    assert len(fingerprints) == 3
    assert _plan(mission_id, 48).horizon_hours == 48
    # simulated synoptic storm peaks mid-window, so waves at +48h exceed NOW
    assert b.weather_exposure.max_wave_m > a.weather_exposure.max_wave_m


# ------------------------------------------------- metrics / explanations ---

@pytest.mark.parametrize("mission_id", MISSION_IDS)
def test_metrics_and_explanations_are_consistent(mission_id):
    resp = _plan(mission_id)
    profile_speed = resp.vessel.cruise_speed_kt * 1.852
    for r in resp.routes:
        si = r.sea_ice_exposure
        assert abs(si.passable_pct + si.caution_pct + si.restricted_pct + si.impassable_pct - 100.0) < 0.5
        assert r.eta_hours >= r.distance_km / profile_speed - 1e-6  # never faster than open-water cruise
        expected_fuel = r.distance_km * r.estimated_fuel.consumption_t_per_km * r.estimated_fuel.environmental_multiplier
        assert abs(r.estimated_fuel.tonnes - expected_fuel) / expected_fuel < 0.01
        assert r.estimated_fuel.environmental_multiplier >= 1.0
        ib = r.iceberg_exposure
        classes = [i.classification for i in ib.relevant_icebergs]
        assert ib.intersecting_count == classes.count("INTERSECTING")
        assert ib.potential_count == classes.count("POTENTIAL")
        assert ib.nearby_count == classes.count("NEARBY")
        assert ib.min_distance_km == (ib.relevant_icebergs[0].distance_km if ib.relevant_icebergs else None)
        # driver == argmax of shares; explanation quotes the route's own numbers
        assert r.risk_driver_shares[r.primary_risk_driver] == max(r.risk_driver_shares.values())
        text = " ".join(r.explanation)
        assert f"{r.distance_km:.0f} km" in text and f"{r.eta_hours:.0f} h" in text
        assert f"{r.estimated_fuel.tonnes:.0f} t fuel" in text
        assert f"{r.risk_score:.2f}" in text and r.primary_risk_driver in text
        assert f"{si.max_sic_pct:.0f}%" in text and si.assessment in text
        assert "PROTOTYPE" in text
    levels = {"VERY LOW": 0.10, "LOW": 0.25, "MEDIUM": 0.45, "HIGH": 0.65}
    for r in resp.routes:
        assert r.risk_level == next((k for k, hi in levels.items() if r.risk_score < hi), "CRITICAL")
    rec = _routes(resp)["recommended"]
    assert any("Compared with LOW-RISK ALTERNATIVE" in line for line in rec.explanation)
    w = resp.weights  # explanation quotes the caller's weights, not the generating search's
    assert f"risk {w.risk:.0%} / fuel {w.fuel:.0%} / ETA {w.eta:.0%}" in " ".join(rec.explanation)


def test_low_risk_and_fast_roles_reflect_measured_metrics():
    r = _routes(_plan("CAPE_TOWN_TO_MAITRI"))
    assert r["low_risk"].risk_score < r["fast_fuel"].risk_score
    assert r["fast_fuel"].eta_hours < r["low_risk"].eta_hours
    assert r["fast_fuel"].estimated_fuel.tonnes < r["low_risk"].estimated_fuel.tonnes


# --------------------------------------------------- passability / vessel ---

def test_default_passability_thresholds_and_configurability():
    assert (DEFAULT_ICE_THRESHOLDS.passable_max, DEFAULT_ICE_THRESHOLDS.caution_max, DEFAULT_ICE_THRESHOLDS.restricted_max) == (0.30, 0.60, 0.80)
    base = _routes(_plan("CAPE_TOWN_TO_MAITRI"))["recommended"].sea_ice_exposure
    strict = _post(
        mission_id="CAPE_TOWN_TO_MAITRI",
        ice_thresholds={"passable_max": 0.1, "caution_max": 0.2, "restricted_max": 0.3},
    ).json()["routes"][0]["sea_ice_exposure"]
    assert strict["passable_pct"] < base.passable_pct
    assert strict["impassable_pct"] > base.impassable_pct


def test_vessel_ice_class_maps_to_constraint_profile():
    assert profile_for_ice_class("Arc7 / ULA").tier == "HEAVY_ICEBREAKER"
    assert profile_for_ice_class("Polar Class 3 (PC3)").tier == "HEAVY_ICEBREAKER"
    assert profile_for_ice_class("DNV ICE-10 / PC5").tier == "ICE_STRENGTHENED"
    assert profile_for_ice_class("Arc5 / UL").tier == "ICE_STRENGTHENED"
    assert profile_for_ice_class("no ice class").tier == "LIMITED_ICE_CAPABILITY"
    heavy = _routes(_plan("CAPE_TOWN_TO_BHARATI"))["recommended"]  # Golovnin, Arc7
    resp = _post(mission_id="CAPE_TOWN_TO_BHARATI", vessel_id="agulhas_ii").json()
    assert resp["vessel"]["profile_tier"] == "ICE_STRENGTHENED"
    assert resp["routes"][0]["estimated_fuel"]["consumption_t_per_km"] < 0.078
    assert heavy.sea_ice_exposure.vessel_ice_class == "Arc7 / ULA"


# --------------------------------------------------------------------- API ---

def test_mission_plan_endpoint_shape():
    resp = _post(mission_id="CAPE_TOWN_TO_BHARATI", horizon_hours=24)
    assert resp.status_code == 200
    body = resp.json()
    assert body["mission_label"] == "CAPE TOWN → BHARATI" and body["horizon_hours"] == 24
    assert abs(sum(body["weights"].values()) - 1.0) < 1e-9
    required = {
        "route_id", "label", "coordinates", "distance_km", "eta_hours", "estimated_fuel", "risk_score",
        "confidence", "sea_ice_exposure", "iceberg_exposure", "weather_exposure", "primary_risk_driver",
        "explanation", "provenance",
    }
    for route in body["routes"]:
        assert required <= route.keys()


@pytest.mark.parametrize(
    "body,status",
    [
        ({"mission_id": "CAPE_TOWN_TO_MARS"}, 422),
        ({"mission_id": "CAPE_TOWN_TO_MAITRI", "horizon_hours": 30}, 422),
        ({"mission_id": "CAPE_TOWN_TO_MAITRI", "weights": {"risk": 0, "fuel": 0, "eta": 0}}, 422),
        ({"mission_id": "CAPE_TOWN_TO_MAITRI", "weights": {"risk": -1, "fuel": 1, "eta": 1}}, 422),
        ({"mission_id": "CAPE_TOWN_TO_MAITRI", "vessel_id": "not_a_ship"}, 404),
        ({"mission_id": "CAPE_TOWN_TO_MAITRI", "ice_thresholds": {"passable_max": 0.7, "caution_max": 0.5, "restricted_max": 0.8}}, 422),
    ],
)
def test_mission_plan_rejects_bad_requests(body, status):
    assert client.post("/mission/plan", json=body).status_code == status


def test_deterministic():
    a = plan_mission(MissionPlanRequest(mission_id="CAPE_TOWN_TO_MAITRI", horizon_hours=48), snapshot=build_snapshot(48))
    b = plan_mission(MissionPlanRequest(mission_id="CAPE_TOWN_TO_MAITRI", horizon_hours=48), snapshot=build_snapshot(48))
    assert [r.coordinates for r in a.routes] == [r.coordinates for r in b.routes]
    assert [r.risk_score for r in a.routes] == [r.risk_score for r in b.routes]


# --------------------------------------------- start position override ---
# Exercised by the shore<->ship coordination workflow (boreas_core.coordination)
# for an underway replan: the vessel's current position, not the mission's
# fixed origin (e.g. Cape Town), becomes the search's start cell.


def test_start_override_begins_near_the_given_point_not_the_mission_origin():
    # Roughly mid-corridor for Bharati, well clear of Cape Town.
    start_lon, start_lat = 45.0, -55.0
    plan = plan_mission(
        MissionPlanRequest(mission_id="CAPE_TOWN_TO_BHARATI", start_lon=start_lon, start_lat=start_lat)
    )
    assert plan.domain.origin_snap_km < 60
    assert "Current position" in plan.origin_name
    mission = MISSIONS["CAPE_TOWN_TO_BHARATI"]
    for route in plan.routes:
        assert route.coordinates[0] == [start_lon, start_lat]
        assert route.coordinates[-1] == list(mission.destination)
        # first vertex is near the override, not near Cape Town
        cape_town_km = haversine_km_array(*route.coordinates[1], *mission.origin)
        override_km = haversine_km_array(*route.coordinates[1], start_lon, start_lat)
        assert override_km < cape_town_km


def test_start_override_requires_both_coordinates():
    resp = client.post(
        "/mission/plan", json={"mission_id": "CAPE_TOWN_TO_BHARATI", "start_lon": 45.0}
    )
    assert resp.status_code == 422


def test_start_override_still_out_of_domain_rejected():
    resp = client.post(
        "/mission/plan",
        json={"mission_id": "CAPE_TOWN_TO_BHARATI", "start_lon": 45.0, "start_lat": -10.0},
    )
    assert resp.status_code == 422
