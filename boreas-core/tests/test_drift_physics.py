import numpy as np
import pytest

from boreas_core.physics.drift import PhysicsDriftModel, constant_forcing
from boreas_core.physics.forces import coriolis_parameter
from boreas_core.physics.geometry import IcebergGeometry


def make_geometry() -> IcebergGeometry:
    return IcebergGeometry(length_m=4000, width_m=1500, thickness_m=250)


def test_geometry_hydrostatic_balance():
    geo = make_geometry()
    # Archimedes: rho_ice * total_volume == rho_seawater * submerged_volume
    assert geo.draft_m + geo.freeboard_m == pytest.approx(geo.thickness_m)
    assert geo.rho_ice * geo.thickness_m == pytest.approx(geo.rho_seawater * geo.draft_m)
    assert geo.mass_kg > 0
    assert geo.sail_area_m2 > 0
    assert geo.draft_area_m2 > geo.sail_area_m2  # draft >> freeboard for tabular bergs


def test_coriolis_parameter_sign_by_hemisphere():
    assert coriolis_parameter(-65.0) < 0  # Southern Hemisphere
    assert coriolis_parameter(65.0) > 0  # Northern Hemisphere
    assert coriolis_parameter(0.0) == pytest.approx(0.0, abs=1e-12)


def test_drag_decelerates_iceberg_with_no_forcing():
    """With zero wind/current, drag must monotonically remove kinetic energy."""
    model = PhysicsDriftModel(geometry=make_geometry())
    result = model.simulate(
        start_lon=0.0,
        start_lat=-65.0,
        start_velocity=np.array([0.5, 0.0]),
        forcing_fn=constant_forcing(np.zeros(2), np.zeros(2)),
        duration_hours=12,
        dt_seconds=600,
    )
    speeds = np.linalg.norm(result.velocity, axis=1)
    assert np.all(np.diff(speeds) <= 1e-9), "speed should be non-increasing under pure drag"
    assert speeds[-1] < speeds[0]


def test_current_forcing_advects_iceberg_downstream():
    """A steady eastward current should carry the iceberg east."""
    model = PhysicsDriftModel(geometry=make_geometry())
    result = model.simulate(
        start_lon=0.0,
        start_lat=-65.0,
        start_velocity=np.zeros(2),
        forcing_fn=constant_forcing(np.zeros(2), np.array([0.3, 0.0])),
        duration_hours=48,
        dt_seconds=900,
    )
    assert result.lon[-1] > result.lon[0]
    final_speed = np.linalg.norm(result.velocity[-1])
    assert 0 < final_speed < 0.3  # water drag alone can't exceed the current speed


def test_coriolis_deflects_left_in_southern_hemisphere():
    """A southward current should deflect east (to its left) south of the equator."""
    model = PhysicsDriftModel(geometry=make_geometry())
    result = model.simulate(
        start_lon=0.0,
        start_lat=-65.0,
        start_velocity=np.zeros(2),
        forcing_fn=constant_forcing(np.zeros(2), np.array([0.0, -0.3])),
        duration_hours=72,
        dt_seconds=900,
    )
    # Moving south (facing south), "left" is east -> longitude should increase.
    assert result.lon[-1] > result.lon[0]


def test_residual_correction_hook_shifts_trajectory():
    geo = make_geometry()
    baseline = PhysicsDriftModel(geometry=geo).simulate(
        start_lon=0.0,
        start_lat=-65.0,
        start_velocity=np.zeros(2),
        forcing_fn=constant_forcing(np.array([5.0, 0.0]), np.array([0.2, 0.0])),
        duration_hours=24,
        dt_seconds=900,
    )
    corrected = PhysicsDriftModel(
        geometry=geo,
        residual_correction=lambda _ctx: np.array([0.0, 0.05]),
    ).simulate(
        start_lon=0.0,
        start_lat=-65.0,
        start_velocity=np.zeros(2),
        forcing_fn=constant_forcing(np.array([5.0, 0.0]), np.array([0.2, 0.0])),
        duration_hours=24,
        dt_seconds=900,
    )
    assert corrected.lat[-1] > baseline.lat[-1]
