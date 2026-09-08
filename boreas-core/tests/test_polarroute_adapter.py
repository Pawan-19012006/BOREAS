import numpy as np

from boreas_core.routing.polarroute_adapter import plan_polar_route

# 32x32 grid matching the real /forecast/ensemble-grid axis convention
# (icenet_mp/ingestion/sources/synthetic.py: lat ascending -90..90, lon
# ascending -180..180).
ICE_LAT = np.linspace(-90, 90, 32)
ICE_LON = np.linspace(-180, 180, 32)


def test_plan_polar_route_returns_available_route_for_open_water():
    ice_mean = np.full((32, 32), 0.1)  # light, well-navigable ice everywhere

    result = plan_polar_route(
        start_lonlat=(10.0, -65.0),
        goal_lonlat=(14.0, -66.5),
        ice_lat=ICE_LAT,
        ice_lon=ICE_LON,
        ice_mean=ice_mean,
        cell_size_deg=1.5,
        padding_deg=2.0,
    )

    assert result.available is True
    assert len(result.path_lonlat) >= 2
    assert result.total_distance_km > 0
    assert result.total_traveltime_hours > 0
    assert "PolarRoute" in result.note


def test_plan_polar_route_degrades_gracefully_when_fully_ice_blocked():
    # SDA's max_ice_conc is 80% -- 95% everywhere makes the whole mesh
    # inaccessible, which must surface as available=False, not an exception.
    ice_mean = np.full((32, 32), 0.95)

    result = plan_polar_route(
        start_lonlat=(10.0, -65.0),
        goal_lonlat=(14.0, -66.5),
        ice_lat=ICE_LAT,
        ice_lon=ICE_LON,
        ice_mean=ice_mean,
        cell_size_deg=1.5,
        padding_deg=2.0,
    )

    assert result.available is False
    assert result.path_lonlat == []
    assert result.note


def test_plan_polar_route_never_raises_on_degenerate_input():
    # Start == goal is a degenerate case that should still degrade cleanly
    # rather than raise, whatever PolarRoute's internal behaviour is.
    ice_mean = np.full((32, 32), 0.1)

    result = plan_polar_route(
        start_lonlat=(10.0, -65.0),
        goal_lonlat=(10.0, -65.0),
        ice_lat=ICE_LAT,
        ice_lon=ICE_LON,
        ice_mean=ice_mean,
        cell_size_deg=1.5,
        padding_deg=2.0,
    )

    assert isinstance(result.available, bool)
