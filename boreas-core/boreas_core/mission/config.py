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


# --- Route strategies -------------------------------------------------------
# The three routes are three operational strategies, not three settings an
# operator dials in. Navigation risk is a CONSTRAINT applied by the engine,
# never a preference weight the shore operator tunes: a candidate is
# "risk-acceptable" when its measured risk score is within
# RISK_ACCEPTANCE_BAND of the safest candidate the engine could find. The band
# is relative (not an absolute ceiling) so the constraint is always feasible --
# an Antarctic station approach is never risk-free, and a fixed ceiling would
# simply reject every route on the hard legs.
RISK_ACCEPTANCE_BAND = 0.08

ROUTE_STRATEGIES = {
    "recommended": {
        "label": "RECOMMENDED",
        "objective": "Balanced operational route",
        "rationale": (
            "Best overall ETA and fuel trade-off among routes that stay within the "
            "navigation-risk limit."
        ),
    },
    "low_risk": {
        "label": "LOW-RISK",
        "objective": "Minimize navigation risk",
        "rationale": "Lowest navigation risk of every route available on this leg.",
    },
    # route_id stays `fast_fuel` so existing API/coordination contracts keep
    # working; the objective it actually optimises is fuel, and the label now
    # says so.
    "fast_fuel": {
        "label": "FUEL-EFFICIENT",
        "objective": "Minimize estimated fuel consumption",
        "rationale": (
            "Lowest estimated fuel burn among routes that stay within the navigation-risk limit."
        ),
    },
}


# --- Route geometry simplification -----------------------------------------
# A* moves on an 8-connected grid, so in uniform open water it approximates a
# straight line with a staircase of alternating diagonal/orthogonal steps.
# Those bends are an artefact of the lattice, not of the environment. After the
# search, a shortcut is taken whenever the straight line between two vertices
# crosses cells no worse than the sub-path it replaces -- so a bend only
# survives when something real (ice, an iceberg exclusion zone, land) made the
# direct line more expensive. SIMPLIFY_TOLERANCE is how much extra cell penalty
# a shortcut may pick up and still be considered "no worse".
SIMPLIFY_TOLERANCE = 0.02
# Below this cell penalty a retained bend is not attributed to a named hazard:
# the cost difference is real but too small to honestly call sea ice or an
# iceberg the cause.
DEVIATION_MIN_PENALTY = 0.08
# A blocked shortcut can be rejected by a cell far from the bend itself --
# extending a long leg slightly changes its whole bearing, so the cell that
# kills it may sit thousands of km away near the other end. That attribution is
# true of the rejected shortcut but useless as a local explanation, and drawing
# it would put a "landmass" label on open ocean half a map away. Beyond this
# distance the bend is reported as generic navigation cost instead of being
# pinned on a hazard the operator cannot see near it.
DEVIATION_MAX_CAUSE_DISTANCE_KM = 400.0


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
