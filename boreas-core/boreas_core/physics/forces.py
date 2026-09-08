"""Force-balance physics for iceberg drift: air drag, water drag, Coriolis.

References the classical drift-force formulation used in operational iceberg
drift models (e.g. Bigg et al. 1997, "Modelling the dynamics and thermodynamics
of icebergs"; Smith 1993 leeway drift studies): a quadratic drag law for both
air and water, plus the Coriolis deflection from Earth's rotation.
"""

import numpy as np

RHO_AIR = 1.225  # kg/m^3 at sea level
EARTH_ANGULAR_VELOCITY = 7.2921159e-5  # rad/s

# Bulk drag coefficients from the iceberg-drift literature. These are the
# dominant source of model uncertainty; the residual-correction model
# (physics/residual_model.py) exists precisely to absorb error from treating
# them as constants.
DEFAULT_AIR_DRAG_COEFFICIENT = 1.3
DEFAULT_WATER_DRAG_COEFFICIENT = 1.5


def coriolis_parameter(latitude_deg: float) -> float:
    """f = 2 * Omega * sin(latitude). Negative in the Southern Hemisphere."""
    lat_rad = np.radians(latitude_deg)
    return 2.0 * EARTH_ANGULAR_VELOCITY * np.sin(lat_rad)


def quadratic_drag_force(
    relative_velocity: np.ndarray,
    *,
    fluid_density: float,
    drag_coefficient: float,
    area_m2: float,
) -> np.ndarray:
    """F = 0.5 * rho * Cd * A * |v_rel| * v_rel, directed along the relative flow."""
    speed = np.linalg.norm(relative_velocity)
    return 0.5 * fluid_density * drag_coefficient * area_m2 * speed * relative_velocity


def coriolis_acceleration(velocity: np.ndarray, latitude_deg: float) -> np.ndarray:
    """a = f * (v_y, -v_x). Deflects motion left in the Southern Hemisphere (f < 0)."""
    f = coriolis_parameter(latitude_deg)
    u, v = velocity
    return np.array([f * v, -f * u])


def net_acceleration(
    *,
    iceberg_velocity: np.ndarray,
    wind_velocity: np.ndarray,
    current_velocity: np.ndarray,
    latitude_deg: float,
    mass_kg: float,
    sail_area_m2: float,
    draft_area_m2: float,
    air_drag_coefficient: float = DEFAULT_AIR_DRAG_COEFFICIENT,
    water_drag_coefficient: float = DEFAULT_WATER_DRAG_COEFFICIENT,
) -> np.ndarray:
    """dV/dt for an iceberg under wind drag + water drag + Coriolis deflection."""
    wind_force = quadratic_drag_force(
        wind_velocity - iceberg_velocity,
        fluid_density=RHO_AIR,
        drag_coefficient=air_drag_coefficient,
        area_m2=sail_area_m2,
    )
    water_force = quadratic_drag_force(
        current_velocity - iceberg_velocity,
        fluid_density=1025.0,
        drag_coefficient=water_drag_coefficient,
        area_m2=draft_area_m2,
    )
    drag_acceleration = (wind_force + water_force) / mass_kg
    return drag_acceleration + coriolis_acceleration(iceberg_velocity, latitude_deg)
