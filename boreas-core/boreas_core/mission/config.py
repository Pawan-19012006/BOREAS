"""Mission definitions, vessel constraint profiles, and prototype thresholds
for the BOREAS Cape Town -> Indian Antarctic station mission planner.

Everything here is a transparent, configurable PROTOTYPE assumption -- none of
the thresholds or consumption figures are scientifically or operationally
validated.
"""

from dataclasses import dataclass

from boreas_core.vessels.roster import CAPE_TOWN_PORT

VALID_HORIZONS_HOURS = (0, 12, 24, 48, 72, 96, 120)


@dataclass(frozen=True)
class MissionDef:
    mission_id: str
    label: str
    origin_name: str
    origin: tuple[float, float]  # (lon, lat)
    destination_name: str
    destination: tuple[float, float]  # (lon, lat)
    default_vessel_id: str


# Station coordinates match frontend/src/data/checkpoints.ts (Bharati
# 69°24'29"S 76°11'14"E, Maitri 70°46'00"S 11°43'55"E).
MISSIONS: dict[str, MissionDef] = {
    "CAPE_TOWN_TO_BHARATI": MissionDef(
        mission_id="CAPE_TOWN_TO_BHARATI",
        label="CAPE TOWN → BHARATI",
        origin_name="Cape Town",
        origin=CAPE_TOWN_PORT,
        destination_name="Bharati Station",
        destination=(76.187361, -69.408030),
        default_vessel_id="vasiliy_golovnin",
    ),
    "CAPE_TOWN_TO_MAITRI": MissionDef(
        mission_id="CAPE_TOWN_TO_MAITRI",
        label="CAPE TOWN → MAITRI",
        origin_name="Cape Town",
        origin=CAPE_TOWN_PORT,
        destination_name="Maitri Station",
        destination=(11.731944, -70.766667),
        default_vessel_id="ivan_papanin",
    ),
}


# --- Coarse navigation domain (covers Cape Town through the Antarctic coast) ---
DOMAIN_LON_RANGE = (-10.0, 95.0)
DOMAIN_LAT_RANGE = (-71.0, -33.0)
DOMAIN_RESOLUTION_DEG = 1.0


# --- Sea-ice passability (PROTOTYPE PASSABILITY MODEL) ---
@dataclass(frozen=True)
class IceThresholds:
    """Upper SIC bounds (0-1) of PASSABLE / CAUTION / RESTRICTED; anything
    above `restricted_max` is IMPASSABLE."""

    passable_max: float = 0.30
    caution_max: float = 0.60
    restricted_max: float = 0.80


DEFAULT_ICE_THRESHOLDS = IceThresholds()
PASSABILITY_LEVELS = ("PASSABLE", "CAUTION", "RESTRICTED", "IMPASSABLE")


# --- Vessel constraint profiles (derived from the observed vessel's ice class) ---
@dataclass(frozen=True)
class VesselProfile:
    tier: str
    cruise_speed_kt: float
    fuel_t_per_km: float  # open-water consumption, PROTOTYPE
    ice_risk_scale: float  # multiplies sea-ice risk (better ice class -> lower)
    ice_resistance_scale: float  # scales ice speed loss and ice fuel penalty


_PROFILES = {
    "HEAVY_ICEBREAKER": VesselProfile("HEAVY_ICEBREAKER", 12.0, 0.078, 0.75, 0.70),
    "ICE_STRENGTHENED": VesselProfile("ICE_STRENGTHENED", 12.0, 0.066, 0.90, 0.90),
    "LIMITED_ICE_CAPABILITY": VesselProfile("LIMITED_ICE_CAPABILITY", 11.0, 0.058, 1.25, 1.20),
}

_HEAVY_MARKERS = ("PC1", "PC2", "PC3", "ARC7", "ULA")
_MEDIUM_MARKERS = ("PC4", "PC5", "ARC4", "ARC5", "ARC6", "ICE-10")


def profile_for_ice_class(ice_class: str) -> VesselProfile:
    text = ice_class.upper()
    if any(m in text for m in _HEAVY_MARKERS):
        return _PROFILES["HEAVY_ICEBREAKER"]
    if any(m in text for m in _MEDIUM_MARKERS):
        return _PROFILES["ICE_STRENGTHENED"]
    return _PROFILES["LIMITED_ICE_CAPABILITY"]


# Iceberg risk_level -> multiplier on the proximity risk around that berg.
BERG_RISK_FACTOR = {"low": 0.5, "guarded": 0.75, "high": 0.9, "critical": 1.0}
