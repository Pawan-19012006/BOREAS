"""The single interpretation of "can this hull go there".

WHY THIS MODULE EXISTS
----------------------
The map and the router used to answer that question separately: the map banded
sea-ice concentration into PASSABLE/CAUTION/RESTRICTED/IMPASSABLE, while the
router merely made high concentrations expensive (`MAX_PENALTY = 0.94`, below
A*'s 0.95 block threshold). Nothing was ever actually blocked, so a route could
run straight through water the legend had just coloured IMPASSABLE. The two were
telling different stories about the same cell.

Everything that needs to classify ice now calls this module -- the routing cost
field, the post-search validator, the route metrics, and the map (via the
`navigable_limit_sic` the plan response carries). There is one answer.

TWO DISTINCT QUESTIONS
----------------------
They were previously conflated, which is what made "IMPASSABLE" ambiguous:

  1. What is the ICE LIKE here?  -> `classify_sic`, an absolute description of
     the floe: PASSABLE / CAUTION / RESTRICTED / IMPASSABLE. A physical fact
     about the water, independent of who is sailing through it.

  2. Can THIS HULL enter it?     -> `navigable_limit_sic` / `is_navigable`, which
     depend on the vessel's ice class.

These genuinely differ. Bharati and Maitri sit in 98-100% concentration fast
ice; an Arc7/ULA icebreaker reaches them every season, a general cargo ship
never could. Treating ">80% = blocked for everyone" would make both stations
permanently unreachable and the planner would return no route at all -- an
internally consistent product that does nothing. Treating it as free passage is
the contradiction this module was written to remove.
"""

from .config import IceThresholds, VesselProfile

# Highest sea-ice concentration each hull class can force, as a fraction.
#
# PROTOTYPE figures, not from any ice-navigation manual. The ordering is the
# part that carries meaning: a purpose-built polar icebreaker can work its way
# into fast ice that would stop an ice-strengthened ship, which in turn goes
# where an unstrengthened hull cannot. Entering ice near the limit is permitted,
# never cheap -- the cost field makes it punishing long before it becomes
# impossible.
NAVIGABLE_LIMIT_BY_TIER = {
    # Breaking heavy ice is the vessel's purpose; it is limited by cost and
    # prudence rather than by a concentration ceiling.
    "HEAVY_ICEBREAKER": 1.0,
    "ICE_STRENGTHENED": 0.90,
    "LIMITED_ICE_CAPABILITY": 0.80,
}


def classify_sic(sic: float, thresholds: IceThresholds) -> str:
    """The absolute ice condition at a cell: what the water is like.

    This is what the map's four bands describe. It says nothing about whether a
    particular hull may enter -- see `is_navigable` for that.
    """
    if sic > thresholds.restricted_max:
        return "IMPASSABLE"
    if sic > thresholds.caution_max:
        return "RESTRICTED"
    if sic > thresholds.passable_max:
        return "CAUTION"
    return "PASSABLE"


def navigable_limit_sic(profile: VesselProfile) -> float:
    """The highest concentration this hull may enter. Above it, the cell is a
    hard block for the router -- not an expensive cell, an unavailable one."""
    return NAVIGABLE_LIMIT_BY_TIER[profile.tier]


def is_navigable(sic, profile: VesselProfile):
    """Whether this hull may enter water of this concentration. Accepts scalars
    or arrays; the array form is what masks the routing grid."""
    return sic <= navigable_limit_sic(profile)
