"""Synthetic iceberg-drift observations for residual-model training.

STATUS: standing in for real data access. BOREAS design doc §5.3 specifies
SIDDA (Sentinel-1 SAR drift vectors) and the BYU/NIC consolidated iceberg
tracking database as ground truth; both require a registered MOSDAC / NIC
data-access agreement this environment does not have. This generator
produces physically-consistent synthetic (feature, residual) pairs so the
residual-learning pipeline (training, evaluation, SHAP explainability) can be
built and tested end-to-end today. Swapping in real drift vectors only
requires replacing `generate_synthetic_drift_dataset` with a loader that
reads SIDDA/BYU-NIC records into the same feature schema.

The synthetic "true" drift = physics-model drift + unmodelled effects the
force-balance in physics/forces.py deliberately excludes (Stokes drift from
surface waves, and a small sub-grid ocean-eddy component), plus observation
noise. This makes the residual-learning task non-trivial and representative
of why residual correction is needed in the first place: real drift deviates
from the physics baseline in structured, learnable ways, not just noise.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from boreas_core.physics.forces import net_acceleration
from boreas_core.physics.geometry import IcebergGeometry

FEATURE_COLUMNS = [
    "physics_vel_east",
    "physics_vel_north",
    "wind_east",
    "wind_north",
    "current_east",
    "current_north",
    "latitude",
    "length_m",
    "width_m",
    "thickness_m",
    "sail_area_m2",
    "draft_area_m2",
]
TARGET_COLUMNS = ["residual_east", "residual_north"]


@dataclass
class SyntheticDriftDataset:
    features: pd.DataFrame
    targets: pd.DataFrame

    @property
    def X(self) -> np.ndarray:
        return self.features[FEATURE_COLUMNS].to_numpy()

    @property
    def y(self) -> np.ndarray:
        return self.targets[TARGET_COLUMNS].to_numpy()


def _unmodelled_effects(wind: np.ndarray, latitude: float, rng: np.random.Generator) -> np.ndarray:
    """Stokes drift (a few % of wind speed, roughly wind-aligned) plus a small
    stochastic eddy term -- structured, physically-motivated effects the
    quadratic drag force model does not capture.
    """
    stokes = 0.02 * wind
    eddy_scale = 0.03 * (1.0 + 0.5 * np.cos(np.radians(latitude)))
    eddy = rng.normal(0, eddy_scale, size=2)
    return stokes + eddy


def generate_synthetic_drift_dataset(
    n_samples: int = 4000, *, seed: int = 0
) -> SyntheticDriftDataset:
    rng = np.random.default_rng(seed)

    rows_features = []
    rows_targets = []

    for _ in range(n_samples):
        latitude = rng.uniform(-78, -55)
        geometry = IcebergGeometry(
            length_m=rng.uniform(200, 6000),
            width_m=rng.uniform(150, 3000),
            thickness_m=rng.uniform(50, 300),
        )
        iceberg_velocity = rng.normal(0, 0.15, size=2)
        wind = rng.normal(0, 8.0, size=2)  # Southern Ocean: strong prevailing winds
        current = rng.normal(0, 0.3, size=2)  # ACC + coastal currents, m/s

        physics_accel = net_acceleration(
            iceberg_velocity=iceberg_velocity,
            wind_velocity=wind,
            current_velocity=current,
            latitude_deg=latitude,
            mass_kg=geometry.mass_kg,
            sail_area_m2=geometry.sail_area_m2,
            draft_area_m2=geometry.draft_area_m2,
        )
        # One-hour-equivalent physics velocity increment, used as the
        # "physics-predicted velocity" feature/baseline for this sample.
        physics_velocity = iceberg_velocity + physics_accel * 3600.0

        true_extra = _unmodelled_effects(wind, latitude, rng)
        observed_velocity = physics_velocity + true_extra
        residual = observed_velocity - physics_velocity  # == true_extra, by construction

        rows_features.append(
            {
                "physics_vel_east": physics_velocity[0],
                "physics_vel_north": physics_velocity[1],
                "wind_east": wind[0],
                "wind_north": wind[1],
                "current_east": current[0],
                "current_north": current[1],
                "latitude": latitude,
                "length_m": geometry.length_m,
                "width_m": geometry.width_m,
                "thickness_m": geometry.thickness_m,
                "sail_area_m2": geometry.sail_area_m2,
                "draft_area_m2": geometry.draft_area_m2,
            }
        )
        rows_targets.append({"residual_east": residual[0], "residual_north": residual[1]})

    return SyntheticDriftDataset(
        features=pd.DataFrame(rows_features), targets=pd.DataFrame(rows_targets)
    )
