"""A lon/lat hazard grid: the shared representation A*, the RL policy, and the
explainability layer all reason over.
"""

from dataclasses import dataclass

import numpy as np

EARTH_RADIUS_KM = 6371.0


@dataclass
class RiskGrid:
    """A regular lon/lat grid with a per-cell navigation risk in [0, 1].

    Risk = 0 is open water; risk = 1 is impassable (e.g. dense pack ice, or an
    iceberg exclusion buffer from `uncertainty/fallback.py`).
    """

    lons: np.ndarray  # (W,) cell-center longitudes, ascending
    lats: np.ndarray  # (H,) cell-center latitudes, ascending
    risk: np.ndarray  # (H, W) in [0, 1]

    def __post_init__(self) -> None:
        if self.risk.shape != (len(self.lats), len(self.lons)):
            raise ValueError("risk grid shape must be (len(lats), len(lons))")
        if np.any((self.risk < 0) | (self.risk > 1)):
            raise ValueError("risk values must be in [0, 1]")

    @property
    def shape(self) -> tuple[int, int]:
        return self.risk.shape

    def nearest_index(self, lon: float, lat: float) -> tuple[int, int]:
        row = int(np.argmin(np.abs(self.lats - lat)))
        col = int(np.argmin(np.abs(self.lons - lon)))
        return row, col

    def cell_center(self, row: int, col: int) -> tuple[float, float]:
        return float(self.lons[col]), float(self.lats[row])

    def in_bounds(self, row: int, col: int) -> bool:
        h, w = self.shape
        return 0 <= row < h and 0 <= col < w

    def is_blocked(self, row: int, col: int, *, blocked_threshold: float = 0.95) -> bool:
        return bool(self.risk[row, col] >= blocked_threshold)

    def stamp_circular_hazard(
        self, *, center_lon: float, center_lat: float, radius_km: float, level: float = 1.0
    ) -> None:
        """Mark cells within `radius_km` of a point at least `level` risky.

        Used to project iceberg positions (and their uncertainty buffers, see
        `uncertainty/fallback.py`) onto the routing grid as hazards.
        """
        lon_scale = EARTH_RADIUS_KM * np.radians(1.0) * np.cos(np.radians(center_lat))
        lat_scale = EARTH_RADIUS_KM * np.radians(1.0)
        lon_grid, lat_grid = np.meshgrid(self.lons, self.lats)
        dist_km = np.hypot(
            (lon_grid - center_lon) * lon_scale, (lat_grid - center_lat) * lat_scale
        )
        mask = dist_km <= radius_km
        self.risk[mask] = np.maximum(self.risk[mask], level)

    def haversine_km(self, a: tuple[int, int], b: tuple[int, int]) -> float:
        lon1, lat1 = self.cell_center(*a)
        lon2, lat2 = self.cell_center(*b)
        p1, p2 = np.radians(lat1), np.radians(lat2)
        dphi = np.radians(lat2 - lat1)
        dlambda = np.radians(lon2 - lon1)
        h = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
        return float(2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(h)))


def synthetic_southern_ocean_grid(
    *, lon_range=(-180, 180), lat_range=(-78, -55), resolution_deg=1.0, seed=0
) -> RiskGrid:
    """A grid with a smooth pack-ice gradient near the continent plus random floes,
    for tests, RL training, and demos where a live OSI-SAF feed isn't wired up yet.
    """
    rng = np.random.default_rng(seed)
    lons = np.arange(lon_range[0], lon_range[1], resolution_deg)
    lats = np.arange(lat_range[0], lat_range[1], resolution_deg)
    lat_grid, _ = np.meshgrid(lats, lons, indexing="ij")

    # Risk increases toward the continent (more southerly latitudes).
    base_risk = np.clip((lat_grid - lat_range[0]) / (lat_range[1] - lat_range[0]), 0, 1)
    base_risk = 1.0 - base_risk  # higher risk further south
    noise = rng.uniform(-0.1, 0.1, size=base_risk.shape)
    risk = np.clip(base_risk * 0.6 + noise, 0.0, 1.0)
    return RiskGrid(lons=lons, lats=lats, risk=risk)
