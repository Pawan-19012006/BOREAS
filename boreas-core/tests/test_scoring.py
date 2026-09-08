from boreas_core.routing.directions import RouteLeg
from boreas_core.routing.scoring import (
    ScoredCandidate,
    lead_step_for_eta_hours,
    rank_candidates,
    time_aware_max_risk,
)


def test_lead_step_for_eta_hours_clamps_to_max():
    assert lead_step_for_eta_hours(0.0, max_lead_step=1) == 0
    assert lead_step_for_eta_hours(23.0, max_lead_step=1) == 0
    assert lead_step_for_eta_hours(25.0, max_lead_step=1) == 1
    assert lead_step_for_eta_hours(1000.0, max_lead_step=1) == 1  # clamped, not out of range


def test_time_aware_max_risk_uses_different_lead_steps_for_early_vs_late_legs():
    # Two lead-step grids that disagree sharply at the same location, so the
    # test actually exercises which lead step gets picked rather than
    # passing by coincidence.
    lat = [0.0, 10.0]
    lon = [0.0, 10.0]
    grid_day0 = [[0.1, 0.1], [0.1, 0.1]]
    grid_day1 = [[0.9, 0.9], [0.9, 0.9]]

    # A single very long leg -> ETA lands in lead_step 1 (day 2), so the
    # reported risk should reflect grid_day1, not grid_day0.
    long_leg = [RouteLeg(start_lonlat=(0.0, 0.0), end_lonlat=(10.0, 10.0), bearing_deg=45.0, compass_label="NE", distance_km=2000.0)]
    risk_far = time_aware_max_risk(
        long_leg, vessel_speed_kt=10.0, ice_lat=lat, ice_lon=lon, ice_mean_by_lead_step=[grid_day0, grid_day1]
    )
    assert risk_far == 0.9

    # A short leg to the same endpoint -> ETA lands in lead_step 0 (day 1).
    short_leg = [RouteLeg(start_lonlat=(0.0, 0.0), end_lonlat=(10.0, 10.0), bearing_deg=45.0, compass_label="NE", distance_km=50.0)]
    risk_near = time_aware_max_risk(
        short_leg, vessel_speed_kt=10.0, ice_lat=lat, ice_lon=lon, ice_mean_by_lead_step=[grid_day0, grid_day1]
    )
    assert risk_near == 0.1


def test_time_aware_max_risk_empty_legs_is_zero():
    assert time_aware_max_risk([], vessel_speed_kt=10.0, ice_lat=[0.0], ice_lon=[0.0], ice_mean_by_lead_step=[[[0.5]]]) == 0.0


def test_rank_candidates_marks_exactly_one_recommended():
    # Equal distance/duration isolates risk as the only differentiator --
    # normalizing identical values yields 0 for all three, so the combined
    # score here is purely `WEIGHT_RISK * normalized_risk`, and the lowest
    # -risk candidate must win regardless of the other weights.
    candidates = [
        ScoredCandidate(key="a", label="A", distance_km=1000, duration_hours=100, risk=0.8),
        ScoredCandidate(key="b", label="B", distance_km=1000, duration_hours=100, risk=0.1),
        ScoredCandidate(key="c", label="C", distance_km=1000, duration_hours=100, risk=0.5),
    ]
    ranked = rank_candidates(candidates)
    recommended = [c for c in ranked if c.recommended]
    assert len(recommended) == 1
    assert recommended[0].key == "b"


def test_rank_candidates_single_candidate_is_recommended():
    candidates = [ScoredCandidate(key="only", label="Only", distance_km=100, duration_hours=10, risk=0.5)]
    ranked = rank_candidates(candidates)
    assert ranked[0].recommended is True


def test_rank_candidates_empty_list():
    assert rank_candidates([]) == []
