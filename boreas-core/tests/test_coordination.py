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
    """Rewinds a vessel's running clock so its SIMULATED voyage has visibly
    advanced, without sleeping in the test.

    Rewinds `running_since` (the start of the current running interval), which
    is what `_elapsed_sim_hours` integrates from. A frozen vessel has no running
    interval, so this deliberately does nothing to it -- which is exactly the
    property the freeze tests assert.
    """
    active = coordination_service._active_routes[vessel_id]
    if active.running_since is None:
        return
    past = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    coordination_service._active_routes[vessel_id] = active.model_copy(
        update={"running_since": past.isoformat()}
    )


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

    before_state = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    assert before_state["distance_travelled_km"] > 0.0, "vessel must have moved before replanning"

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

    # ...and the voyage's history survives the swap. The new route starts where
    # the vessel is, so its OWN along-track distance restarts at zero, but
    # mission progress must not: the ship has really sailed that distance.
    assert new_state["distance_travelled_km"] >= before_state["distance_travelled_km"] - 5.0
    assert new_state["distance_travelled_km"] > 0.0
    assert new_state["progress_fraction"] > 0.0
    assert active["distance_travelled_before_km"] == pytest.approx(
        before_state["distance_travelled_km"], abs=30.0
    )

    # The accepted route begins at the vessel's actual position.
    assert active["start_offset_km"] is not None
    assert active["start_offset_km"] < 25.0

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


# ------------------------------------------- active-route lifecycle guarantees ---


def test_exactly_one_active_route_survives_acceptance():
    """The core invariant: accepting REPLACES the active route. The superseded
    route must not remain active anywhere in the canonical store, because that
    is what let Shore draw two competing routes at once."""
    vessel_id = "agulhas_ii"
    _, old_route, _ = _activate(vessel_id)
    _backdate(vessel_id, seconds=25)

    preview = client.post(
        "/coordination/simulate-environment-change", json={"vessel_id": vessel_id}
    ).json()
    update = client.post("/coordination/route-updates", json=preview).json()
    client.post(
        f"/coordination/route-updates/{update['update_id']}/respond", json={"status": "ACCEPTED"}
    )

    # One entry per vessel, and it is the NEW route.
    assert len([v for v in coordination_service._active_routes if v == vessel_id]) == 1
    active = coordination_service._active_routes[vessel_id]
    assert active.route.route_id == preview["new_route"]["route_id"]
    assert active.route.coordinates != old_route.coordinates

    # And the vessel state answers against the new route, not the old one.
    state = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    assert state["route_id"] == preview["new_route"]["route_id"]


def test_accepted_route_starts_at_current_position_not_at_port():
    """Requirement 3: the accepted route must begin where the vessel is, never
    back at Cape Town."""
    vessel_id = "le_commandant_charcot"
    plan, _, _ = _activate(vessel_id)
    # At 1x the clock is deliberately slow, so wind it well forward to get the
    # vessel clear of port before replanning.
    _backdate(vessel_id, seconds=600)

    state_before = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    preview = client.post(
        "/coordination/simulate-environment-change", json={"vessel_id": vessel_id}
    ).json()
    update = client.post("/coordination/route-updates", json=preview).json()
    client.post(
        f"/coordination/route-updates/{update['update_id']}/respond", json={"status": "ACCEPTED"}
    )

    active = client.get(f"/coordination/active-route/{vessel_id}").json()
    first_lon, first_lat = active["route"]["coordinates"][0]

    # Starts at the vessel, within a fraction of a degree.
    assert abs(first_lon - state_before["longitude"]) < 0.5
    assert abs(first_lat - state_before["latitude"]) < 0.5

    # And emphatically NOT back at the mission origin.
    origin_lon, origin_lat = plan.routes[0].coordinates[0]
    assert abs(first_lon - origin_lon) + abs(first_lat - origin_lat) > 1.0

    # The destination is unchanged -- a replan changes the path, not the goal.
    assert active["route"]["coordinates"][-1] == plan.routes[0].coordinates[-1]


def test_progress_does_not_reset_on_acceptance():
    """Requirement 4/10: progress, travelled distance and position all carry
    across the swap; only remaining distance is recomputed from here."""
    vessel_id = "akademik_fedorov"
    _activate(vessel_id)
    _backdate(vessel_id, seconds=40)

    before = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    preview = client.post(
        "/coordination/simulate-environment-change", json={"vessel_id": vessel_id}
    ).json()
    update = client.post("/coordination/route-updates", json=preview).json()
    client.post(
        f"/coordination/route-updates/{update['update_id']}/respond", json={"status": "ACCEPTED"}
    )

    after = client.get(f"/coordination/vessel-state/{vessel_id}").json()

    assert after["progress_fraction"] > 0.0, "progress must not reset to zero"
    assert after["distance_travelled_km"] == pytest.approx(
        before["distance_travelled_km"], rel=0.10, abs=10.0
    )
    # Remaining is measured along the NEW route from the current position.
    assert after["distance_remaining_km"] > 0.0
    assert after["distance_remaining_km"] == pytest.approx(
        preview["new_route"]["distance_km"], rel=0.10, abs=50.0
    )


def test_declining_preserves_the_original_active_route_and_progress():
    """A declined update must change nothing at all."""
    vessel_id = "xue_long_2"
    _, old_route, _ = _activate(vessel_id)
    _backdate(vessel_id, seconds=20)

    before = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    preview = client.post(
        "/coordination/simulate-environment-change", json={"vessel_id": vessel_id}
    ).json()
    update = client.post("/coordination/route-updates", json=preview).json()
    client.post(
        f"/coordination/route-updates/{update['update_id']}/respond", json={"status": "DECLINED"}
    )

    active = client.get(f"/coordination/active-route/{vessel_id}").json()
    assert active["route"]["route_id"] == old_route.route_id
    assert active["route"]["coordinates"] == old_route.coordinates
    assert active["supersedes_update_id"] is None

    after = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    assert after["distance_travelled_km"] >= before["distance_travelled_km"]


def test_initial_activation_reports_no_start_offset():
    """`start_offset_km` is about a replan handoff; the first activation from
    port has no prior position to compare against and must not invent one."""
    vessel_id = "vasiliy_golovnin"
    _activate(vessel_id)
    active = client.get(f"/coordination/active-route/{vessel_id}").json()
    assert active["start_offset_km"] is None
    assert active["distance_travelled_before_km"] == 0.0


# ------------------------------------------- navigation lifecycle / freezing ---


def test_planning_alone_does_not_start_telemetry():
    """Planning must never move the vessel: with no ActiveRoute there is no
    vessel state at all, so nothing can be ticking.

    Clears the store entry explicitly rather than relying on this vessel never
    having been activated by another test in this module, which would make the
    assertion depend on file ordering.
    """
    vessel_id = "le_commandant_charcot"
    coordination_service._active_routes.pop(vessel_id, None)

    _plan(vessel_id=vessel_id)  # planning only -- deliberately no activation

    assert client.get(f"/coordination/vessel-state/{vessel_id}").status_code == 404
    assert client.get(f"/coordination/active-route/{vessel_id}").status_code == 404


def test_activation_starts_the_clock_running():
    """START NAVIGATION is the single commit: activating the route is what puts
    the vessel under way, with telemetry live from that moment."""
    vessel_id = "agulhas_ii"
    _activate(vessel_id)
    state = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    assert state["is_under_way"] is True
    assert state["paused_reason"] is None
    assert state["speed_multiplier"] == 1.0
    assert state["speed_kt"] > 0


def test_one_times_speed_is_slow_and_the_multiplier_scales_it():
    """1x must be the slow, realistic pace and 12x must genuinely be 12 times
    it -- 1x behaving like 12x is the thing being guarded against here."""
    vessel_id = "kronprins_haakon"
    _activate(vessel_id)

    # Compare distance covered over identical simulated intervals by driving the
    # clock directly rather than sleeping.
    _backdate(vessel_id, seconds=10)
    at_1x = client.get(f"/coordination/vessel-state/{vessel_id}").json()["distance_travelled_km"]

    _activate(vessel_id)
    client.post(f"/coordination/vessel-state/{vessel_id}/speed", json={"multiplier": 12})
    _backdate(vessel_id, seconds=10)
    at_12x = client.get(f"/coordination/vessel-state/{vessel_id}").json()["distance_travelled_km"]

    assert at_1x > 0
    assert at_12x == pytest.approx(12 * at_1x, rel=0.05)


def test_speed_change_does_not_rewrite_distance_already_sailed():
    """Switching to 12x must accelerate what happens NEXT, not retroactively
    rescale the voyage so far."""
    vessel_id = "agulhas_ii"
    _activate(vessel_id)
    _backdate(vessel_id, seconds=20)
    before = client.get(f"/coordination/vessel-state/{vessel_id}").json()["distance_travelled_km"]

    after = client.post(
        f"/coordination/vessel-state/{vessel_id}/speed", json={"multiplier": 12}
    ).json()
    assert after["speed_multiplier"] == 12.0
    assert after["distance_travelled_km"] == pytest.approx(before, abs=2.0)


def test_rejects_an_unsupported_speed_multiplier():
    vessel_id = "agulhas_ii"
    _activate(vessel_id)
    assert (
        client.post(f"/coordination/vessel-state/{vessel_id}/speed", json={"multiplier": 7}).status_code
        == 422
    )


def test_environment_change_freezes_the_vessel_at_a_captured_position():
    """The heart of the deterministic replan: the trigger captures one position,
    the vessel stops there, and it does not drift while the proposal stands."""
    vessel_id = "le_commandant_charcot"
    _activate(vessel_id)
    _backdate(vessel_id, seconds=25)

    preview = client.post(
        "/coordination/simulate-environment-change", json={"vessel_id": vessel_id}
    ).json()

    snapshot = preview["origin_snapshot"]
    assert snapshot is not None

    frozen = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    assert frozen["is_under_way"] is False
    assert frozen["paused_reason"] == "AWAITING_ROUTE_DECISION"
    assert frozen["speed_kt"] == 0.0

    # The proposed route starts AT the snapshot, not at the mission origin.
    first_lon, first_lat = preview["new_route"]["coordinates"][0]
    assert first_lon == pytest.approx(snapshot["longitude"], abs=0.01)
    assert first_lat == pytest.approx(snapshot["latitude"], abs=0.01)

    # Winding the clock forward must not move a frozen vessel.
    _backdate(vessel_id, seconds=60)
    still = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    assert still["longitude"] == pytest.approx(frozen["longitude"], abs=1e-6)
    assert still["latitude"] == pytest.approx(frozen["latitude"], abs=1e-6)
    assert still["distance_travelled_km"] == pytest.approx(frozen["distance_travelled_km"], abs=1e-6)


def test_acceptance_activates_from_the_snapshot_and_resumes_movement():
    vessel_id = "kronprins_haakon"
    _activate(vessel_id)
    client.post(f"/coordination/vessel-state/{vessel_id}/speed", json={"multiplier": 4})
    _backdate(vessel_id, seconds=25)

    preview = client.post(
        "/coordination/simulate-environment-change", json={"vessel_id": vessel_id}
    ).json()
    snapshot = preview["origin_snapshot"]
    update = client.post("/coordination/route-updates", json=preview).json()
    assert update["origin_snapshot"] == snapshot

    frozen = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    client.post(
        f"/coordination/route-updates/{update['update_id']}/respond", json={"status": "ACCEPTED"}
    )

    active = client.get(f"/coordination/active-route/{vessel_id}").json()
    # Activated from the exact frozen position.
    assert active["start_offset_km"] == pytest.approx(0.0, abs=1.0)
    # The operator's chosen demo speed survives the swap.
    assert active["speed_multiplier"] == 4.0

    after = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    assert after["is_under_way"] is True, "movement must resume once the decision is made"
    assert after["progress_fraction"] > 0.0, "progress must not reset"
    assert after["longitude"] == pytest.approx(frozen["longitude"], abs=0.2)
    assert after["latitude"] == pytest.approx(frozen["latitude"], abs=0.2)


def test_decline_resumes_movement_on_the_original_route():
    """Declining changes no route, but must not leave the vessel stranded frozen."""
    vessel_id = "le_commandant_charcot"
    _, old_route, _ = _activate(vessel_id)
    _backdate(vessel_id, seconds=25)

    preview = client.post(
        "/coordination/simulate-environment-change", json={"vessel_id": vessel_id}
    ).json()
    update = client.post("/coordination/route-updates", json=preview).json()

    assert client.get(f"/coordination/vessel-state/{vessel_id}").json()["is_under_way"] is False

    client.post(
        f"/coordination/route-updates/{update['update_id']}/respond", json={"status": "DECLINED"}
    )

    active = client.get(f"/coordination/active-route/{vessel_id}").json()
    assert active["route"]["coordinates"] == old_route.coordinates

    after = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    assert after["is_under_way"] is True
    assert after["route_id"] == old_route.route_id


def test_shore_and_ship_read_one_vessel_state():
    """There is a single canonical state; two readers cannot disagree."""
    vessel_id = "agulhas_ii"
    _activate(vessel_id)
    _backdate(vessel_id, seconds=15)
    # Freeze so the two reads are not separated by real elapsed time.
    client.post(f"/coordination/vessel-state/{vessel_id}/pause", json={})

    shore = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    ship = client.get(f"/coordination/vessel-state/{vessel_id}").json()
    for field in ("longitude", "latitude", "progress_fraction", "route_id", "speed_multiplier"):
        assert shore[field] == ship[field]
