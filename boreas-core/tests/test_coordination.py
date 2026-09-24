"""Tests for the shore<->ship coordination layer: activating a route,
computing a vessel's SIMULATED position along it, proposing/sending a
RouteUpdate, and the Captain accepting/declining it.

`activate_route` validates vessel_id against the real roster (the same one
`/mission/plan` itself uses), so tests use real roster ids, not invented
ones. `boreas_core.coordination` also keeps process-global mutable state (an
in-memory active-route / route-update store keyed by vessel_id), so each
test is assigned its own dedicated roster vessel to avoid cross-test
interference rather than resetting module globals.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from boreas_core.api.server import app
from boreas_core.coordination import service as coordination_service
from boreas_core.mission import MissionPlanRequest, plan_mission

client = TestClient(app)


def _plan(mission_id="CAPE_TOWN_TO_BHARATI", **kw):
    return plan_mission(MissionPlanRequest(mission_id=mission_id, **kw))


def _activate(vessel_id, mission_id="CAPE_TOWN_TO_BHARATI", route=None):
    plan = _plan(mission_id, vessel_id=vessel_id)
    route = route or next(r for r in plan.routes if r.route_id == "recommended")
    resp = client.post(
        "/coordination/active-route",
        json={"mission_id": mission_id, "vessel_id": vessel_id, "route": route.model_dump()},
    )
    assert resp.status_code == 201, resp.text
    return plan, route, resp.json()


def _backdate(vessel_id: str, seconds: float) -> None:
    """Rewinds a vessel's activated_at so its SIMULATED clock has visibly
    advanced, without sleeping in the test."""
    active = coordination_service._active_routes[vessel_id]
    past = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    coordination_service._active_routes[vessel_id] = active.model_copy(update={"activated_at": past.isoformat()})


# ------------------------------------------------------------- active route ---


def test_activate_and_fetch_active_route():
    vessel_id = "vasiliy_golovnin"
    _, route, body = _activate(vessel_id)
    assert body["mission_id"] == "CAPE_TOWN_TO_BHARATI"
    assert body["vessel_id"] == vessel_id
    assert body["route"]["route_id"] == route.route_id
    assert body["horizon_hours"] == route.iceberg_exposure.horizon_hours
    assert body["supersedes_update_id"] is None

    fetched = client.get(f"/coordination/active-route/{vessel_id}")
    assert fetched.status_code == 200
    assert fetched.json()["route"]["route_id"] == route.route_id


def test_active_route_404_before_activation():
    vessel_id = "polarstern"  # never activated by any other test in this file
    assert client.get(f"/coordination/active-route/{vessel_id}").status_code == 404
    assert client.get(f"/coordination/vessel-state/{vessel_id}").status_code == 404


# --------------------------------------------------------------- telemetry ---


def test_vessel_state_starts_at_route_origin_and_advances():
    vessel_id = "sir_david_attenborough"
    _, route, _ = _activate(vessel_id)

    fresh = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    assert fresh["route_id"] == route.route_id
    assert fresh["distance_travelled_km"] < 1.0  # just activated
    assert fresh["progress_fraction"] < 0.01
    assert not fresh["is_complete"]
    assert abs(fresh["longitude"] - route.coordinates[0][0]) < 0.5
    assert abs(fresh["latitude"] - route.coordinates[0][1]) < 0.5
    assert fresh["next_waypoint_index"] >= 1
    assert fresh["distance_to_next_waypoint_km"] > 0
    assert "SIMULATED" in fresh["provenance"]

    # Rewind the clock to simulate real elapsed time without sleeping.
    _backdate(vessel_id, seconds=30)
    later = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    assert later["distance_travelled_km"] > fresh["distance_travelled_km"]
    assert later["progress_fraction"] > fresh["progress_fraction"]
    assert later["heading_deg"] is not None
    assert later["speed_kt"] > 0


def test_vessel_state_completes_at_full_transit_time():
    vessel_id = "xue_long_2"
    _, route, _ = _activate(vessel_id)
    # Rewind well past the route's own ETA.
    _backdate(vessel_id, seconds=(route.eta_hours / coordination_service.TIME_ACCELERATION_HOURS_PER_SECOND) * 2)
    state = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    assert state["is_complete"] is True
    assert state["progress_fraction"] == 1.0
    assert state["speed_kt"] == 0.0
    assert state["heading_deg"] is None
    assert abs(state["longitude"] - route.coordinates[-1][0]) < 0.5
    assert abs(state["latitude"] - route.coordinates[-1][1]) < 0.5


# ------------------------------------------------------------------ mission ---


def test_mission_info_known_and_unknown():
    ok = client.get("/coordination/mission/CAPE_TOWN_TO_MAITRI")
    assert ok.status_code == 200
    body = ok.json()
    assert body["origin_name"] == "Cape Town"
    assert body["destination_name"] == "Maitri Station"

    assert client.get("/coordination/mission/CAPE_TOWN_TO_MARS").status_code == 404


# -------------------------------------------------------- simulate + propose ---


def test_simulate_environment_change_produces_a_genuinely_different_real_route():
    vessel_id = "kronprins_haakon"
    _, old_route, _ = _activate(vessel_id)
    _backdate(vessel_id, seconds=15)  # so current_position isn't exactly the origin

    resp = client.post("/coordination/simulate-environment-change", json={"vessel_id": vessel_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["mission_id"] == "CAPE_TOWN_TO_BHARATI"
    assert body["vessel_id"] == vessel_id
    assert body["old_route"]["route_id"] == old_route.route_id
    assert body["reason"]  # non-empty, honest, backend-numbers-derived
    assert "real backend forecast" in body["reason"]

    new_route = body["new_route"]
    # The new route starts from the vessel's current (simulated) position at
    # the instant this request was served, not back at Cape Town. (Not
    # re-checked against a fresh GET here: the voyage clock is continuously
    # advancing, so a later read would legitimately differ.)
    assert new_route["coordinates"][0] == body["current_position"]
    assert new_route["coordinates"][0] != list(_plan().routes[0].coordinates[0])
    # A materially different hazard snapshot (advanced horizon) -- the route
    # is a real, independently-planned output, not the same one repeated.
    assert new_route["iceberg_exposure"]["horizon_hours"] > old_route.iceberg_exposure.horizon_hours


def test_simulate_environment_change_without_active_route_404s():
    resp = client.post(
        "/coordination/simulate-environment-change", json={"vessel_id": "le_commandant_charcot"}
    )
    assert resp.status_code == 404


# -------------------------------------------------------------- full workflow ---


def test_full_accept_workflow_ship_continues_from_current_position():
    vessel_id = "ivan_papanin"
    _, old_route, _ = _activate(vessel_id)
    _backdate(vessel_id, seconds=20)

    preview = client.post(
        "/coordination/simulate-environment-change", json={"vessel_id": vessel_id}
    ).json()

    created = client.post("/coordination/route-updates", json=preview)
    assert created.status_code == 201, created.text
    update = created.json()
    assert update["status"] == "PENDING"
    assert update["old_route_id"] == old_route.route_id
    assert update["new_route_id"] == preview["new_route"]["route_id"]
    assert update["distance_delta"] == pytest.approx(
        preview["new_route"]["distance_km"] - preview["old_route"]["distance_km"], abs=0.05
    )
    assert update["eta_delta"] == pytest.approx(
        preview["new_route"]["eta_hours"] - preview["old_route"]["eta_hours"], abs=0.05
    )
    assert update["risk_delta"] == pytest.approx(
        preview["new_route"]["risk_score"] - preview["old_route"]["risk_score"], abs=1e-3
    )

    # Ship polls and sees it pending.
    pending = client.get(
        "/coordination/route-updates", params={"vessel_id": vessel_id, "status": "PENDING"}
    ).json()
    assert any(u["update_id"] == update["update_id"] for u in pending)

    fetched = client.get(f"/coordination/route-updates/{update['update_id']}")
    assert fetched.status_code == 200

    # Captain accepts.
    accepted = client.post(
        f"/coordination/route-updates/{update['update_id']}/respond", json={"status": "ACCEPTED"}
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "ACCEPTED"
    assert accepted.json()["responded_at"] is not None

    active = client.get(f"/coordination/active-route/{vessel_id}").json()
    assert active["route"]["route_id"] == preview["new_route"]["route_id"]
    assert active["supersedes_update_id"] == update["update_id"]

    # The ship's position right after acceptance is exactly where it was
    # right before -- no jump back to Cape Town.
    new_state = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    assert abs(new_state["longitude"] - preview["current_position"][0]) < 0.5
    assert abs(new_state["latitude"] - preview["current_position"][1]) < 0.5
    assert new_state["distance_travelled_km"] < 5.0  # clock reset, journey continues from here

    # Responding twice is rejected.
    again = client.post(
        f"/coordination/route-updates/{update['update_id']}/respond", json={"status": "DECLINED"}
    )
    assert again.status_code == 409


def test_decline_leaves_active_route_unchanged():
    vessel_id = "nuyina"
    _, old_route, _ = _activate(vessel_id)
    _backdate(vessel_id, seconds=10)

    preview = client.post(
        "/coordination/simulate-environment-change", json={"vessel_id": vessel_id}
    ).json()
    update = client.post("/coordination/route-updates", json=preview).json()

    declined = client.post(
        f"/coordination/route-updates/{update['update_id']}/respond", json={"status": "DECLINED"}
    )
    assert declined.status_code == 200
    assert declined.json()["status"] == "DECLINED"

    active = client.get(f"/coordination/active-route/{vessel_id}").json()
    assert active["route"]["route_id"] == old_route.route_id
    assert active["supersedes_update_id"] is None


def test_respond_to_unknown_update_404s():
    resp = client.post(
        "/coordination/route-updates/upd_doesnotexist/respond", json={"status": "ACCEPTED"}
    )
    assert resp.status_code == 404


def test_list_route_updates_filters_by_vessel_and_status():
    vessel_a, vessel_b = "akademik_fedorov", "agulhas_ii"
    _activate(vessel_a)
    _activate(vessel_b)

    for v in (vessel_a, vessel_b):
        _backdate(v, seconds=10)
        preview = client.post("/coordination/simulate-environment-change", json={"vessel_id": v}).json()
        client.post("/coordination/route-updates", json=preview)

    only_a = client.get("/coordination/route-updates", params={"vessel_id": vessel_a}).json()
    assert all(u["vessel_id"] == vessel_a for u in only_a)
    assert len(only_a) == 1

    all_pending = client.get("/coordination/route-updates", params={"status": "PENDING"}).json()
    assert {u["vessel_id"] for u in all_pending} >= {vessel_a, vessel_b}
