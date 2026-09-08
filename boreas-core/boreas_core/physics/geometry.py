"""Iceberg geometry -> mass and drag-relevant areas.

Icebergs are modelled as rectangular tabular blocks (a standard simplification
for large Antarctic tabular bergs, e.g. B-15, B-17 class). Freeboard/draft
follow hydrostatic (Archimedes) balance between ice and seawater density
rather than a fixed ratio, so geometry stays physically consistent.
"""

from dataclasses import dataclass

RHO_ICE = 900.0  # kg/m^3, typical glacial ice density
RHO_SEAWATER = 1025.0  # kg/m^3


@dataclass(frozen=True)
class IcebergGeometry:
    """A rectangular tabular iceberg of length x width x total thickness."""

    length_m: float
    width_m: float
    thickness_m: float  # total vertical extent (freeboard + draft)
    rho_ice: float = RHO_ICE
    rho_seawater: float = RHO_SEAWATER

    def __post_init__(self) -> None:
        if self.length_m <= 0 or self.width_m <= 0 or self.thickness_m <= 0:
            raise ValueError("Iceberg dimensions must be positive.")
        if not 0 < self.rho_ice < self.rho_seawater:
            raise ValueError("Require 0 < rho_ice < rho_seawater for it to float.")

    @property
    def draft_m(self) -> float:
        """Submerged depth, from Archimedes' principle: rho_ice * V = rho_sw * V_submerged."""
        return self.thickness_m * (self.rho_ice / self.rho_seawater)

    @property
    def freeboard_m(self) -> float:
        """Height above the waterline."""
        return self.thickness_m - self.draft_m

    @property
    def mass_kg(self) -> float:
        return self.rho_ice * self.length_m * self.width_m * self.thickness_m

    @property
    def sail_area_m2(self) -> float:
        """Cross-sectional area exposed to wind (above waterline)."""
        return self.width_m * self.freeboard_m

    @property
    def draft_area_m2(self) -> float:
        """Cross-sectional area exposed to ocean current (below waterline)."""
        return self.width_m * self.draft_m
