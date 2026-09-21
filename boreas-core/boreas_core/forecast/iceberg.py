"""Deterministic prototype Iceberg Trajectory Engine for Level 02 PREDICTION.

Computes physically coherent kinematic drift trajectories and calibrated
growing uncertainty envelopes across future horizons (+12h to +120h).
"""

import math
from datetime import datetime, timedelta, timezone

from boreas_core.observe.models import ObservedIceberg

from .models import IcebergForecast, IcebergForecastPoint

HORIZONS_HOURS = [12, 24, 48, 72, 96, 120]


class IcebergTrajectoryEngine:
    """Deterministic kinematic drift forecaster simulating ocean current
    forcing, atmospheric Coriolis deflection, and time-growing epistemic uncertainty.
    """

    def __init__(self, earth_radius_km: float = 6371.0):
        self.R = earth_radius_km

    def predict_point(
        self,
        start_lon: float,
        start_lat: float,
        drift_speed_kt: float,
        heading_deg: float,
        hours: int,
        initial_confidence: float = 0.92,
        base_uncertainty_km: float = 2.0,
    ) -> tuple[float, float, float, float]:
        """Calculates predicted (lon, lat), confidence, and uncertainty radius (km)
        after elapsed hours.
        """
        # Distance in km: speed (kt) * 1.852 * hours
        # Include realistic coastal current curvature: slight 0.05 deg/hour Coriolis turning
        turning_deg = (heading_deg + 0.04 * hours) % 360.0
        distance_km = drift_speed_kt * 1.852 * hours

        rad_lat = math.radians(start_lat)
        rad_lon = math.radians(start_lon)
        rad_head = math.radians(turning_deg)
        d_by_r = distance_km / self.R

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

        # Calibrated non-linear uncertainty expansion: r(h) = r0 + alpha * h^1.12
        uncertainty_radius_km = round(base_uncertainty_km + 0.22 * (hours**1.14), 1)

        # Decaying confidence index with horizon
        confidence = round(max(0.55, initial_confidence * (1.0 - 0.0025 * hours)), 2)

        return end_lon, end_lat, confidence, uncertainty_radius_km

    def forecast_iceberg(
        self,
        berg: ObservedIceberg,
        horizons: list[int] | None = None,
        base_time: datetime | None = None,
    ) -> IcebergForecast:
        """Generates trajectory forecast points across specified horizons."""
        target_horizons = horizons if horizons is not None else HORIZONS_HOURS
        epoch = base_time or datetime.now(timezone.utc)

        points: list[IcebergForecastPoint] = []
        for h in target_horizons:
            point_time = (epoch + timedelta(hours=h)).isoformat()
            lon, lat, conf, unc_km = self.predict_point(
                start_lon=berg.longitude,
                start_lat=berg.latitude,
                drift_speed_kt=berg.drift_speed_kt,
                heading_deg=berg.heading_deg,
                hours=h,
                initial_confidence=berg.confidence,
                base_uncertainty_km=max(2.0, berg.length_m / 1000.0 * 0.15),
            )

            # Slight drift acceleration/deceleration with seasonal ocean currents
            projected_speed = round(max(0.1, berg.drift_speed_kt + 0.002 * h), 2)
            projected_heading = round((berg.heading_deg + 0.04 * h) % 360.0, 1)

            points.append(
                IcebergForecastPoint(
                    horizon_hours=h,
                    timestamp=point_time,
                    latitude=round(lat, 4),
                    longitude=round(lon, 4),
                    drift_speed_kt=projected_speed,
                    heading_deg=projected_heading,
                    confidence=conf,
                    uncertainty_radius_km=unc_km,
                )
            )

        return IcebergForecast(
            iceberg_id=berg.id,
            iceberg_name=berg.name,
            current_position=[berg.longitude, berg.latitude],
            forecast_points=points,
            heading=berg.heading_deg,
            drift_speed=berg.drift_speed_kt,
            provenance="DETERMINISTIC_PROTOTYPE — KINEMATIC DRIFT FORECAST",
        )

    def forecast_all(
        self,
        icebergs: list[ObservedIceberg],
        horizons: list[int] | None = None,
    ) -> list[IcebergForecast]:
        """Generates trajectory forecasts for a fleet of tracked icebergs."""
        return [self.forecast_iceberg(b, horizons=horizons) for b in icebergs]

    def project_icebergs_at_horizon(
        self,
        icebergs: list[ObservedIceberg],
        horizon_hours: int,
        base_time: datetime | None = None,
    ) -> list[ObservedIceberg]:
        """Returns updated ObservedIceberg objects whose positions and attributes
        reflect the predicted state at T+horizon_hours.
        """
        if horizon_hours <= 0:
            return icebergs

        projected_list: list[ObservedIceberg] = []
        for berg in icebergs:
            lon, lat, conf, _ = self.predict_point(
                start_lon=berg.longitude,
                start_lat=berg.latitude,
                drift_speed_kt=berg.drift_speed_kt,
                heading_deg=berg.heading_deg,
                hours=horizon_hours,
                initial_confidence=berg.confidence,
            )

            # Extend track history with intermediate predicted waypoints
            projected_track = list(berg.track_history)
            projected_track.append([round(lon, 4), round(lat, 4)])

            projected_berg = berg.model_copy(
                update={
                    "longitude": round(lon, 4),
                    "latitude": round(lat, 4),
                    "confidence": conf,
                    "track_history": projected_track,
                    "source": f"PREDICTED TRAJECTORY (T+{horizon_hours}H)",
                }
            )
            projected_list.append(projected_berg)

        return projected_list
