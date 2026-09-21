"""Prediction orchestration service combining icebergs, sea-ice, and atmospheric
forecasts into the canonical Unified Future State X(t+h).
"""

import math
from datetime import datetime, timedelta, timezone

from boreas_core.observe.models import ObservedVessel
from boreas_core.observe.service import get_observed_icebergs, get_observed_vessels

from .environment import EnvironmentalForecastEngine
from .iceberg import IcebergTrajectoryEngine
from .models import (
    EnvironmentalForecastPoint,
    EnvironmentalForecastResponse,
    FutureStateResponse,
    IcebergForecast,
    SeaIceForecastResponse,
)
from .sea_ice import SeaIceForecastEngine

_iceberg_engine = IcebergTrajectoryEngine()
_sea_ice_engine = SeaIceForecastEngine()
_environment_engine = EnvironmentalForecastEngine()


def get_iceberg_forecasts(horizon_hours: int | None = None) -> list[IcebergForecast]:
    """Returns iceberg drift forecasts for all tracked targets."""
    icebergs = get_observed_icebergs().icebergs
    horizons = [horizon_hours] if horizon_hours is not None else None
    return _iceberg_engine.forecast_all(icebergs, horizons=horizons)


def get_sea_ice_forecast(horizon_hours: int = 72) -> SeaIceForecastResponse:
    """Returns spatial sea-ice concentration grid prediction for given horizon."""
    return _sea_ice_engine.predict_grid(horizon_hours=horizon_hours)


def get_environmental_forecast(horizon_hours: int | None = None) -> EnvironmentalForecastResponse:
    """Returns meteorological and sea-state forecast points."""
    return _environment_engine.get_full_forecast()


def _project_vessels_forward(
    vessels: list[ObservedVessel],
    hours: int,
    earth_radius_km: float = 6371.0,
) -> list[ObservedVessel]:
    """Projects underway vessels forward along dead-reckoning vectors while
    keeping moored vessels stationary and ice-bound vessels drifting with ice.
    """
    if hours <= 0:
        return vessels

    projected: list[ObservedVessel] = []
    for v in vessels:
        if v.status == "MOORED":
            projected.append(v)
            continue

        speed_kt = v.speed_kt if v.status != "ICE_BOUND" else 0.4
        heading_deg = v.heading_deg if v.status != "ICE_BOUND" else (v.heading_deg + 20.0) % 360.0

        # Distance traveled in km
        distance_km = speed_kt * 1.852 * hours
        rad_lat = math.radians(v.latitude)
        rad_lon = math.radians(v.longitude)
        rad_head = math.radians(heading_deg)
        d_by_r = distance_km / earth_radius_km

        end_lat_rad = math.asin(
            math.sin(rad_lat) * math.cos(d_by_r)
            + math.cos(rad_lat) * math.sin(d_by_r) * math.cos(rad_head)
        )
        end_lon_rad = rad_lon + math.atan2(
            math.sin(rad_head) * math.sin(d_by_r) * math.cos(rad_lat),
            math.cos(d_by_r) - math.sin(rad_lat) * math.sin(end_lat_rad),
        )

        end_lat = math.degrees(end_lat_rad)
        end_lon = math.degrees(end_lon_rad)

        new_track = list(v.track_history)
        new_track.append([round(end_lon, 4), round(end_lat, 4)])

        projected.append(
            v.model_copy(
                update={
                    "latitude": round(end_lat, 4),
                    "longitude": round(end_lon, 4),
                    "track_history": new_track,
                    "source": f"PROJECTED AIS ESTIMATE (T+{hours}H)",
                }
            )
        )

    return projected


def get_future_state(horizon_hours: int = 72) -> FutureStateResponse:
    """Combines all forecasting engines to produce the canonical FutureState
    representation X(t+h) required for Level 03 Risk Evaluation and Routing.
    """
    epoch = datetime.now(timezone.utc)
    target_time = (epoch + timedelta(hours=horizon_hours)).isoformat()

    current_vessels = get_observed_vessels().vessels
    current_icebergs = get_observed_icebergs().icebergs

    # 1. Project vessels forward
    projected_vessels = _project_vessels_forward(current_vessels, horizon_hours)

    # 2. Project icebergs forward
    projected_icebergs = _iceberg_engine.project_icebergs_at_horizon(
        current_icebergs, horizon_hours, base_time=epoch
    )

    # 3. Predict spatial sea-ice concentration grid
    sea_ice_res = _sea_ice_engine.predict_grid(horizon_hours=horizon_hours, base_time=epoch)

    # 4. Predict atmospheric & wave environment
    env_res = _environment_engine.predict_at_horizon(horizon_hours=horizon_hours, base_time=epoch)

    # Overall fused confidence decays non-linearly with horizon
    overall_conf = round(max(0.60, 0.92 - 0.0024 * horizon_hours), 2)

    provenance = {
        "vessels": f"PROJECTED KINEMATIC AIS (T+{horizon_hours}H)",
        "icebergs": f"DETERMINISTIC DRIFT KINEMATICS (T+{horizon_hours}H)",
        "sea_ice": f"DETERMINISTIC SPATIAL EVOLUTION (T+{horizon_hours}H)",
        "environment": f"SIMULATED SYNOPTIC MODEL (T+{horizon_hours}H)",
    }

    return FutureStateResponse(
        horizon_hours=horizon_hours,
        timestamp=target_time,
        vessels=projected_vessels,
        icebergs=projected_icebergs,
        sea_ice=sea_ice_res,
        environment=env_res,
        overall_confidence=overall_conf,
        provenance=provenance,
    )
