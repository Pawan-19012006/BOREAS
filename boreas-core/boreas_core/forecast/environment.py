"""Deterministic Environmental Forecast service for Level 02 PREDICTION.

Generates synoptically coherent polar atmospheric and marine forcing
predictions across horizons (+12h to +120h).
"""

import math
from datetime import datetime, timedelta, timezone

from .models import EnvironmentalForecastPoint, EnvironmentalForecastResponse

HORIZONS_HOURS = [12, 24, 48, 72, 96, 120]


class EnvironmentalForecastEngine:
    """Predicts atmospheric wind, significant wave height, barometric pressure,
    and thermal forcing across future horizons.
    """

    def predict_at_horizon(
        self,
        horizon_hours: int,
        base_time: datetime | None = None,
    ) -> EnvironmentalForecastPoint:
        epoch = base_time or datetime.now(timezone.utc)
        target_time = (epoch + timedelta(hours=horizon_hours)).isoformat()
        h = float(max(0, horizon_hours))

        # Synoptic polar front wave simulation (3-5 day cyclonic system progression)
        cycle_rad = (h / 72.0) * math.pi

        # Wind speed (kt): baseline 16kt with cyclonic storm peak around 48-72h
        wind_speed = round(16.5 + 8.5 * math.sin(cycle_rad), 1)
        # Wind direction shifts cyclonically with low passage (240 deg -> 290 deg)
        wind_direction = round((245.0 + 35.0 * math.sin(cycle_rad * 0.8)) % 360.0, 1)

        # Significant wave height (m): tightly coupled with wind duration and fetch
        wave_height = round(max(1.2, 2.4 + 1.6 * math.sin(cycle_rad)), 1)

        # Barometric pressure (hPa): drops during cyclonic passage
        pressure = round(984.0 - 18.0 * math.sin(cycle_rad), 1)

        # Surface & air temperatures
        air_temp = round(-12.5 - 4.0 * (h / 120.0) - 3.0 * math.cos(cycle_rad), 1)
        surface_temp = round(-1.4 - 0.3 * (h / 120.0), 1)

        # Visibility (nm): drops in blowing snow / low pressure
        visibility = round(max(2.5, 8.0 - 4.5 * math.sin(cycle_rad)), 1)

        # Confidence decaying from 0.95 (T+0) to 0.70 (T+120)
        confidence = round(max(0.68, 0.95 - 0.0022 * h), 2)

        return EnvironmentalForecastPoint(
            horizon_hours=horizon_hours,
            timestamp=target_time,
            wind_speed_kt=wind_speed,
            wind_direction_deg=wind_direction,
            wave_height_m=wave_height,
            air_temp_c=air_temp,
            surface_temp_c=surface_temp,
            pressure_hpa=pressure,
            visibility_nm=visibility,
            confidence=confidence,
            provenance="SIMULATED SYNOPTIC POLAR FORECAST",
        )

    def get_full_forecast(
        self,
        base_time: datetime | None = None,
    ) -> EnvironmentalForecastResponse:
        current = self.predict_at_horizon(0, base_time=base_time)
        forecasts = [self.predict_at_horizon(h, base_time=base_time) for h in HORIZONS_HOURS]
        return EnvironmentalForecastResponse(
            forecasts=forecasts,
            current=current,
            provenance="SIMULATED SYNOPTIC POLAR FORECAST",
        )
