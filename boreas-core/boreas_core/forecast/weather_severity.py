"""Weather severity: one deterministic score and one category scale, used by
every part of BOREAS that talks about weather.

Severity is computed ONLY from variables the environmental forecast actually
produces (`EnvironmentalForecastPoint`): wind speed, significant wave height and
visibility. Pressure is carried through for display and drives the spatial field
in `weather_field.py`, but it is deliberately NOT a severity term of its own --
a deep low is only a navigation concern through the wind and sea it generates,
and counting it separately would double-count the same physics.

Thresholds live here and nowhere else. The internal score is continuous so it
can enter the routing cost field smoothly; the operator only ever sees the
category.
"""

from dataclasses import dataclass

import numpy as np

# Category boundaries on the 0-1 severity score. The route planner consumes the
# score; the UI consumes the category.
CAUTION_SEVERITY = 0.35
SEVERE_SEVERITY = 0.55
EXTREME_SEVERITY = 0.78

# A region is a "hotspot" once it reaches CAUTION. Anything below is NORMAL and
# is never reported as a hazard region.
HOTSPOT_MIN_SEVERITY = CAUTION_SEVERITY

WEATHER_CATEGORIES = ("NORMAL", "CAUTION", "SEVERE", "EXTREME")

# Per-variable ramps: (value at which the term starts to bite, value at which it
# saturates). Chosen for a mid-size ice-strengthened research/supply vessel in
# the Southern Ocean; PROTOTYPE, not validated against any operating manual.
WIND_RAMP_KT = (22.0, 55.0)
WAVE_RAMP_M = (2.5, 8.0)
VISIBILITY_RAMP_NM = (5.0, 1.0)  # descending: 5 nm starts to bite, 1 nm saturates

# Term weights. Wave height dominates because it, not wind speed alone, is what
# forces a vessel to slow, alter course or heave to.
WIND_WEIGHT = 0.34
WAVE_WEIGHT = 0.50
VISIBILITY_WEIGHT = 0.16


def _ramp(value, low: float, high: float):
    """Normalise `value` onto 0-1 across [low, high]. Handles a descending ramp
    (high < low), which is how visibility works -- less is worse."""
    return np.clip((np.asarray(value, dtype=float) - low) / (high - low), 0.0, 1.0)


def weather_severity(wind_kt, wave_m, visibility_nm) -> np.ndarray:
    """Continuous 0-1 weather severity. Accepts scalars or arrays."""
    return np.clip(
        WIND_WEIGHT * _ramp(wind_kt, *WIND_RAMP_KT)
        + WAVE_WEIGHT * _ramp(wave_m, *WAVE_RAMP_M)
        + VISIBILITY_WEIGHT * _ramp(visibility_nm, *VISIBILITY_RAMP_NM),
        0.0,
        1.0,
    )


def severity_category(severity) -> str:
    """Operator-facing category for a single severity score."""
    s = float(severity)
    if s >= EXTREME_SEVERITY:
        return "EXTREME"
    if s >= SEVERE_SEVERITY:
        return "SEVERE"
    if s >= CAUTION_SEVERITY:
        return "CAUTION"
    return "NORMAL"


@dataclass(frozen=True)
class DriverContribution:
    driver: str
    share: float


def primary_weather_driver(wind_kt: float, wave_m: float, visibility_nm: float) -> str:
    """Which variable is actually responsible for the severity here.

    Returns the driver with the largest weighted contribution, so the label an
    operator reads is the term that genuinely dominates the score rather than a
    guess. `CALM` when nothing contributes at all.
    """
    terms = {
        "HIGH_WIND": WIND_WEIGHT * float(_ramp(wind_kt, *WIND_RAMP_KT)),
        "HEAVY_SEAS": WAVE_WEIGHT * float(_ramp(wave_m, *WAVE_RAMP_M)),
        "LOW_VISIBILITY": VISIBILITY_WEIGHT * float(_ramp(visibility_nm, *VISIBILITY_RAMP_NM)),
    }
    driver, value = max(terms.items(), key=lambda kv: kv[1])
    return driver if value > 0.0 else "CALM"


DRIVER_LABELS = {
    "HIGH_WIND": "High wind",
    "HEAVY_SEAS": "Heavy seas",
    "LOW_VISIBILITY": "Low visibility",
    "CALM": "No dominant driver",
}
