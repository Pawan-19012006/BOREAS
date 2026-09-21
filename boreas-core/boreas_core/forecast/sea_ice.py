"""Deterministic prototype Sea-Ice Forecast Engine for Level 02 PREDICTION.

Provides a clean, replaceable forecasting interface for spatial sea-ice
concentration grids across horizons (+12h to +120h).
"""

import math
from datetime import datetime, timedelta, timezone

import numpy as np

from .models import SeaIceForecastResponse

# Canonical 32x32 Southern Ocean coordinates matching the deep-ensemble grid
GRID_LATS = np.linspace(-90, -45, 32).tolist()
GRID_LONS = np.linspace(-180, 180, 32).tolist()


class SeaIceForecastEngine:
    """Deterministic spatial evolution engine predicting sea-ice concentration
    dynamics under atmospheric cooling and westerly advection.

    Designed as a drop-in interface to be superseded in future production phases
    by an empirical FNO (Fourier Neural Operator) or NEMO-SI3 numerical runs.
    """

    def __init__(self, lats: list[float] | None = None, lons: list[float] | None = None):
        self.lats = lats or GRID_LATS
        self.lons = lons or GRID_LONS

    def predict_grid(
        self,
        horizon_hours: int = 72,
        base_time: datetime | None = None,
    ) -> SeaIceForecastResponse:
        """Generates predicted 2D concentration matrix for given horizon."""
        epoch = base_time or datetime.now(timezone.utc)
        target_time = (epoch + timedelta(hours=horizon_hours)).isoformat()

        h = float(max(0, horizon_hours))
        # Advection displacement: westerly drift ~0.08 deg longitude per hour
        lon_drift_deg = 0.08 * h
        # Coastal ice compaction: slight expansion/freeze rate ~0.015 per 24h
        freeze_factor = 1.0 + 0.02 * (h / 24.0)

        n_lat = len(self.lats)
        n_lon = len(self.lons)
        grid: list[list[float]] = []

        total_conc = 0.0
        max_conc = 0.0
        count = 0

        for r, lat in enumerate(self.lats):
            row: list[float] = []
            # Climatological baseline: lat <= -70 is heavy pack ice (0.85-1.0),
            # lat >= -55 is marginal ice zone / open ocean (0.0-0.2)
            lat_weight = (
                1.0
                if lat <= -72
                else 0.0
                if lat >= -54
                else ((-54 - lat) / 18.0)
            )

            for c, lon in enumerate(self.lons):
                # Advected longitude phase
                shifted_lon = (lon - lon_drift_deg) % 360.0
                rad_lon = math.radians(shifted_lon)

                # Planetary wave harmonics representing Weddell Sea & Ross Sea gyre tongues
                gyre_perturbation = (
                    0.18 * math.sin(rad_lon)
                    + 0.12 * math.cos(2.0 * rad_lon)
                    + 0.08 * math.sin(3.0 * rad_lon + 0.5)
                )

                # Localized Prydz Bay embayment signature around 75 deg E
                prydz_signature = 0.15 * math.exp(-((lon - 76.0) ** 2) / 450.0)

                raw_sic = (lat_weight + gyre_perturbation + prydz_signature) * freeze_factor
                # Clamp within physical boundaries [0.0, 1.0]
                sic = round(float(min(1.0, max(0.0, raw_sic))), 3)

                row.append(sic)
                if lat <= -60:  # Count polar regional cells for operational mean
                    total_conc += sic
                    count += 1
                if sic > max_conc:
                    max_conc = sic

            grid.append(row)

        mean_conc_pct = round((total_conc / max(count, 1)) * 100.0, 1)
        peak_conc_pct = round(max_conc * 100.0, 1)

        # Epistemic confidence degrades non-linearly with forecast lead time
        confidence = round(max(0.62, 0.94 - 0.0022 * h), 2)

        return SeaIceForecastResponse(
            horizon_hours=horizon_hours,
            timestamp=target_time,
            grid_lat=self.lats,
            grid_lon=self.lons,
            sic_values=grid,
            mean_concentration_pct=mean_conc_pct,
            max_concentration_pct=peak_conc_pct,
            confidence=confidence,
            provenance="PROTOTYPE — DETERMINISTIC SPATIAL EVOLUTION",
        )
