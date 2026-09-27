"""Weather hotspot detection, severity semantics, and weather's effect on routing.

The point of these tests is the CAUSAL CHAIN, not the numbers: severe weather
must produce a hotspot, a hotspot must cost the router something, and a route
that crosses one must be more expensive than one that avoids it. Where a test
needs a specific weather field it builds one directly rather than depending on
the seeded synoptic scenario, so the assertions survive a change to the seeds.
"""

import numpy as np
import pytest

from boreas_core.forecast import weather_hotspots as wh
from boreas_core.forecast.models import EnvironmentalForecastPoint
from boreas_core.forecast.weather_field import evaluate_weather, systems_at
from boreas_core.forecast.weather_hotspots import detect_hotspots
from boreas_core.forecast.weather_severity import (
    CAUTION_SEVERITY,
    EXTREME_SEVERITY,
    SEVERE_SEVERITY,
    primary_weather_driver,
    severity_category,
    weather_severity,
)
from boreas_core.mission import MissionPlanRequest, plan_mission
from boreas_core.mission.config import (
    WEATHER_RISK_BY_CATEGORY,
    profile_for_ice_class,
    DEFAULT_ICE_THRESHOLDS,
)
from boreas_core.mission.fields import FieldModel, build_snapshot, domain_axes


@pytest.fixture(autouse=True)
def _clear_hotspot_cache():
    wh._clear_cache_for_tests()
    yield
    wh._clear_cache_for_tests()


# ------------------------------------------------------------------ severity ---


def test_calm_weather_scores_zero_severity():
    assert weather_severity(wind_kt=8.0, wave_m=1.0, visibility_nm=10.0) == pytest.approx(0.0)
    assert severity_category(0.0) == "NORMAL"


def test_severity_rises_monotonically_with_each_variable():
    base = dict(wind_kt=20.0, wave_m=2.0, visibility_nm=10.0)
    s0 = float(weather_severity(**base))
    assert float(weather_severity(**{**base, "wind_kt": 45.0})) > s0
    assert float(weather_severity(**{**base, "wave_m": 6.0})) > s0
    # Visibility is inverted -- less visibility is worse.
    assert float(weather_severity(**{**base, "visibility_nm": 1.0})) > s0


def test_storm_conditions_reach_extreme():
    s = float(weather_severity(wind_kt=60.0, wave_m=9.0, visibility_nm=0.5))
    assert severity_category(s) == "EXTREME"


def test_category_boundaries_are_ordered():
    assert 0.0 < CAUTION_SEVERITY < SEVERE_SEVERITY < EXTREME_SEVERITY <= 1.0
    assert severity_category(CAUTION_SEVERITY) == "CAUTION"
    assert severity_category(SEVERE_SEVERITY) == "SEVERE"
    assert severity_category(EXTREME_SEVERITY) == "EXTREME"


def test_primary_driver_names_the_dominant_variable():
    # Visibility collapsed, wind and sea benign -> visibility must be the driver.
    assert primary_weather_driver(wind_kt=10.0, wave_m=1.0, visibility_nm=0.5) == "LOW_VISIBILITY"
    # Nothing contributing at all.
    assert primary_weather_driver(wind_kt=5.0, wave_m=0.5, visibility_nm=12.0) == "CALM"


# ------------------------------------------------------------------ detection ---


def _uniform_background(**overrides) -> EnvironmentalForecastPoint:
    """A flat, calm synoptic background so a test controls the field entirely."""
    base = dict(
        horizon_hours=0,
        timestamp="2026-01-01T00:00:00+00:00",
        wind_speed_kt=6.0,
        wind_direction_deg=270.0,
        wave_height_m=0.8,
        air_temp_c=-10.0,
        surface_temp_c=-1.0,
        pressure_hpa=1005.0,
        visibility_nm=12.0,
        confidence=0.9,
    )
    base.update(overrides)
    return EnvironmentalForecastPoint(**base)


def _grid():
    lons = np.arange(-10.0, 95.0 + 1e-9, 1.0)
    lats = np.arange(-71.0, -33.0 + 1e-9, 1.0)
    return lons, lats


def test_normal_weather_produces_no_hotspot(monkeypatch):
    """Requirement 1 and 10: calm weather yields no regions, and none are invented."""
    monkeypatch.setattr("boreas_core.forecast.weather_field.systems_at", lambda h: [])
    monkeypatch.setattr(
        "boreas_core.forecast.weather_field.background_state",
        lambda h, base_time=None: _uniform_background(),
    )
    lons, lats = _grid()
    assert detect_hotspots(lons, lats, 0) == []


def test_severe_weather_produces_a_hotspot():
    """Requirement 2: the seeded synoptic scenario yields real regions, and each
    one is at least CAUTION with conditions that justify its category."""
    lons, lats = _grid()
    hotspots = detect_hotspots(lons, lats, 0)
    assert hotspots, "the seeded synoptic scenario must produce at least one region"
    for h in hotspots:
        assert h.severity in ("CAUTION", "SEVERE", "EXTREME")
        assert h.severity_score >= CAUTION_SEVERITY
        assert severity_category(h.severity_score) == h.severity
        assert h.cell_count >= wh.MIN_HOTSPOT_CELLS
        assert h.area_km2 > 0 and h.radius_km > 0
        # Provenance is never optimistic.
        assert h.source == "SIMULATED" and h.mode == "DEMO"


def test_neighbouring_severe_cells_group_into_one_hotspot(monkeypatch):
    """Requirement 3: one region per contiguous blob, not one marker per cell."""
    lons, lats = _grid()

    # A single storm: one system, so one contiguous severe blob.
    monkeypatch.setattr(
        "boreas_core.forecast.weather_field.background_state",
        lambda h, base_time=None: _uniform_background(),
    )
    from boreas_core.forecast.weather_field import CycloneSystem

    one = [CycloneSystem("ONLY", 40.0, -55.0, 600.0, 60.0, 975.0)]
    monkeypatch.setattr("boreas_core.forecast.weather_field.systems_at", lambda h: one)

    hotspots = detect_hotspots(lons, lats, 0)
    assert len(hotspots) == 1, f"one storm must give one region, got {len(hotspots)}"
    # And it must actually span many cells -- proving grouping happened rather
    # than a single cell squeaking through.
    assert hotspots[0].cell_count > 10


def test_separate_severe_regions_stay_separate(monkeypatch):
    """Requirement 4: two well-separated storms are two regions."""
    lons, lats = _grid()
    monkeypatch.setattr(
        "boreas_core.forecast.weather_field.background_state",
        lambda h, base_time=None: _uniform_background(),
    )
    from boreas_core.forecast.weather_field import CycloneSystem

    two = [
        CycloneSystem("WEST", 5.0, -55.0, 400.0, 60.0, 975.0),
        CycloneSystem("EAST", 75.0, -55.0, 400.0, 60.0, 975.0),
    ]
    monkeypatch.setattr("boreas_core.forecast.weather_field.systems_at", lambda h: two)

    hotspots = detect_hotspots(lons, lats, 0)
    assert len(hotspots) == 2
    # Far apart, as seeded -- they were not merged.
    assert abs(hotspots[0].longitude - hotspots[1].longitude) > 50.0


def test_forecast_horizon_moves_the_hotspots():
    """Requirement 5: changing the horizon changes where the regions are, because
    the systems translate. This is what makes the existing timeline control
    weather as well as ice and icebergs."""
    lons, lats = _grid()
    at_0 = {h.hotspot_id: h for h in detect_hotspots(lons, lats, 0)}
    at_48 = detect_hotspots(lons, lats, 48)
    assert at_0 and at_48

    # The systems themselves must have moved east.
    s0 = {s.system_id: s.lon for s in systems_at(0)}
    s48 = {s.system_id: s.lon for s in systems_at(48)}
    for sid in s0:
        assert s48[sid] > s0[sid], f"{sid} did not translate east"

    # And the detected centres must differ between the two horizons.
    centres_0 = sorted(round(h.longitude, 1) for h in at_0.values())
    centres_48 = sorted(round(h.longitude, 1) for h in at_48)
    assert centres_0 != centres_48


def test_detection_is_deterministic():
    """Same horizon, same regions. `valid_time` is excluded because it is an
    absolute wall-clock time derived from "now" -- T+24h genuinely names a
    different instant on each call. The FIELD and the geometry it produces must
    not move, and that is what is asserted."""
    lons, lats = _grid()

    def shape(hotspots):
        return [
            {k: v for k, v in h.model_dump().items() if k != "valid_time"} for h in hotspots
        ]

    assert shape(detect_hotspots(lons, lats, 24)) == shape(detect_hotspots(lons, lats, 24))


# -------------------------------------------------------------------- routing ---


def _field_model(horizon: int) -> FieldModel:
    return FieldModel(build_snapshot(horizon), profile_for_ice_class("Arc7"), DEFAULT_ICE_THRESHOLDS)


def test_severe_weather_costs_the_router_more_than_calm_water():
    """Requirements 6 and 7: crossing a hotspot carries a higher weather risk than
    staying clear of one. This is the mechanism that makes avoidance happen at
    all -- without it the hotspot would be decoration."""
    fm = _field_model(0)
    lons, lats = domain_axes()
    hotspots = detect_hotspots(lons, lats, 0)
    assert hotspots
    worst = max(hotspots, key=lambda h: h.severity_score)

    inside = fm.evaluate(np.array([worst.longitude]), np.array([worst.latitude]))
    # A point on the same latitude but far from every system.
    far_lon = min(
        (lo for lo in lons),
        key=lambda lo: -min(abs(lo - h.longitude) for h in hotspots),
    )
    outside = fm.evaluate(np.array([far_lon]), np.array([worst.latitude]))

    assert float(inside.wx_severity[0]) > float(outside.wx_severity[0])
    assert float(inside.wx_risk[0]) > float(outside.wx_risk[0])
    assert float(inside.risk[0]) > float(outside.risk[0])


def test_weather_risk_respects_the_configured_category_multipliers():
    """The cost the router pays and the category the UI shows come from one table."""
    fm = _field_model(0)
    lons, lats = domain_axes()
    lon_g, lat_g = np.meshgrid(lons, lats)
    f = fm.evaluate(lon_g, lat_g)

    normal = f.wx_severity < CAUTION_SEVERITY
    assert normal.any()
    # Calm water sits at (or just above) the NORMAL anchor, never beyond CAUTION's.
    assert float(f.wx_risk[normal].max()) <= WEATHER_RISK_BY_CATEGORY["CAUTION"] + 1e-9
    assert float(f.wx_risk.min()) >= WEATHER_RISK_BY_CATEGORY["NORMAL"] - 1e-9

    extreme = f.wx_severity >= EXTREME_SEVERITY
    if extreme.any():
        assert float(f.wx_risk[extreme].min()) >= WEATHER_RISK_BY_CATEGORY["SEVERE"]


@pytest.mark.parametrize("horizon", [0, 24, 72])
def test_routes_report_honest_weather_exposure(horizon):
    """Requirement 10 on the route side: the reported figures agree with the
    regions actually detected, and nothing is fabricated."""
    plan = plan_mission(MissionPlanRequest(mission_id="CAPE_TOWN_TO_BHARATI", horizon_hours=horizon))
    detected = {h.hotspot_id for h in detect_hotspots(*domain_axes(), horizon)}

    for route in plan.routes:
        w = route.weather_exposure
        assert w.mode == "DEMO" and w.source == "SIMULATED"
        assert w.exposure_level in ("LOW", "MODERATE", "HIGH")
        assert w.max_severity in ("NORMAL", "CAUTION", "SEVERE", "EXTREME")

        # Every reported encounter is a region the detector really found.
        for e in w.hotspot_encounters:
            assert e.hotspot_id in detected
        # "Crossed" is consistent with the geometry it was derived from.
        assert w.hotspots_crossed == sum(1 for e in w.hotspot_encounters if e.crossed)
        for e in w.hotspot_encounters:
            assert e.crossed == (e.distance_km <= e.radius_km)

        # The closest-severe figure matches the encounters it came from.
        severe = [e.distance_km for e in w.hotspot_encounters if e.severity in ("SEVERE", "EXTREME")]
        if severe:
            assert w.closest_severe_hotspot_km == pytest.approx(round(min(severe), 1))
        else:
            assert w.closest_severe_hotspot_km is None


@pytest.mark.parametrize("horizon", [0, 24])
def test_weather_deviations_point_at_real_weather(horizon):
    """Requirement 9: a bend attributed to weather must have genuinely elevated
    weather at the cell it blames -- no bend is explained by an invented storm."""
    plan = plan_mission(MissionPlanRequest(mission_id="CAPE_TOWN_TO_BHARATI", horizon_hours=horizon))
    fm = _field_model(horizon)

    found_any = False
    for route in plan.routes:
        for d in route.deviations:
            if d.cause != "WEATHER":
                continue
            found_any = True
            f = fm.evaluate(np.array([d.cause_longitude]), np.array([d.cause_latitude]))
            # Materially worse than the open-water baseline.
            assert float(f.wx_risk[0]) > WEATHER_RISK_BY_CATEGORY["NORMAL"]
            # The reported conditions are the field's own values, not decoration.
            assert d.wind_speed_kt == pytest.approx(round(float(f.wind_kt[0]), 1), abs=0.2)
            assert d.wave_height_m == pytest.approx(round(float(f.wave_m[0]), 1), abs=0.2)
            # A cell below CAUTION must not be described as though the severe
            # weather were AT the bend. Naming the region it is approaching (and
            # that region's severity) is accurate; claiming local severe weather
            # is not.
            if d.weather_severity == "NORMAL":
                assert d.detail.lower().startswith(("approach to", "rising wind"))
            else:
                assert d.weather_severity.lower() in d.detail.lower()

    assert found_any, "expected at least one weather-caused bend in the seeded scenario"


def test_extreme_can_be_configured_to_block_routing(monkeypatch):
    """Requirement 8: EXTREME is a very expensive corridor by default, but can be
    turned into a hard navigation constraint."""
    import boreas_core.mission.fields as mf

    lons, lats = domain_axes()
    lon_g, lat_g = np.meshgrid(lons, lats)
    fm = _field_model(0)

    monkeypatch.setattr(mf, "WEATHER_EXTREME_BLOCKS", False)
    soft = fm.evaluate(lon_g, lat_g)
    monkeypatch.setattr(mf, "WEATHER_EXTREME_BLOCKS", True)
    hard = fm.evaluate(lon_g, lat_g)

    extreme = soft.wx_severity >= EXTREME_SEVERITY
    assert extreme.any(), "the seeded scenario must contain EXTREME cells"
    # Soft mode keeps them navigable-but-costly; hard mode pins them at 1.0.
    assert float(soft.wx_risk[extreme].max()) <= 1.0
    assert np.allclose(hard.wx_risk[extreme], 1.0)
    assert float(hard.wx_risk[extreme].min()) >= float(soft.wx_risk[extreme].min())


def test_hotspot_endpoint_reports_demo_mode():
    from fastapi.testclient import TestClient

    from boreas_core.api.server import app

    client = TestClient(app)
    res = client.get("/forecast/weather/hotspots", params={"horizon_hours": 24})
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "DEMO"
    assert body["source"] == "SIMULATED"
    assert body["horizon_hours"] == 24
    assert "thresholds" in body
    for h in body["hotspots"]:
        assert h["severity"] in ("CAUTION", "SEVERE", "EXTREME")

    # An unsupported horizon is rejected rather than silently coerced.
    assert client.get("/forecast/weather/hotspots", params={"horizon_hours": 7}).status_code == 422
