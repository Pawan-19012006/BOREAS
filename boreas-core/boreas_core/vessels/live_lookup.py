"""Real terrestrial-AIS live position lookup against VesselAPI's free tier.

VesselAPI (https://vesselapi.com) was chosen after comparing it against
AISHub (requires running your own AIS receiver -- not a pure API-key
signup), AISstream.io (WebSocket-only, MMSI/bbox lookup, no name/IMO
search), and several paid-only providers (Datalastic, VesselFinder API,
MarineTraffic, MyShipTracking, Datadocked). VesselAPI is the only
candidate offering a genuine no-card-required free tier (150 calls/month)
with REST lookup by IMO number -- see https://vesselapi.com/docs/vessels
and https://vesselapi.com/pricing.

Terrestrial AIS only has ~50km coastal range. A vessel on the Cape Town -
Bharati/Maitri run spends most of its transit in the open Southern Ocean,
far beyond that range -- so a lookup miss there is the *expected*, correct
outcome, not a bug. That is why a coverage gap is reported as its own
"BEYOND AIS RANGE" status rather than folded into a generic error: it is
physically different from "NOT CONNECTED" (missing/invalid API
credentials), which is a configuration problem the operator can fix.

Results of a real round trip (LIVE or BEYOND AIS RANGE) are cached per-IMO
for CACHE_TTL_SECONDS so that GET /vessels/roster -- which looks up every
roster vessel on every call -- doesn't spend one VesselAPI call per vessel
per request against the 150-call/month free tier. Config errors (missing
key, missing IMO) and transient network failures are deliberately *not*
cached, so fixing either takes effect on the very next request rather than
waiting out a stale cache entry.

VesselAPI's own docs (https://vesselapi.com/docs) document remaining quota
via the `X-RateLimit-Remaining` response header (an integer, or the literal
string "Unlimited" on uncapped plans) -- not independently exercised
against a live call in this codebase, so treated defensively (best-effort
parse, silently skipped if absent or non-numeric).
"""

import logging
import os
import time
from dataclasses import dataclass

import httpx

from .roster import RosterVessel

logger = logging.getLogger(__name__)

VESSELAPI_BASE_URL = "https://api.vesselapi.com/v1"
VESSELAPI_KEY_ENV = "VESSELAPI_API_KEY"
CACHE_TTL_SECONDS = 3600.0
LOW_QUOTA_WARNING_THRESHOLD = 20

STATUS_LIVE = "LIVE — terrestrial AIS"
STATUS_BEYOND_RANGE = "BEYOND AIS RANGE"
STATUS_NOT_CONNECTED = "NOT CONNECTED"

# imo -> (cached_at_monotonic, result). Process-lifetime, in-memory -- fine
# for this scope (a single-process API server), not meant to survive a
# restart or be shared across processes.
_CACHE: dict[str, tuple[float, "LiveLookupResult"]] = {}


@dataclass(frozen=True)
class LiveLookupResult:
    status: str
    lon: float
    lat: float
    # Only populated for a genuine live fix -- a fallback position is never
    # given a fabricated "as of" time, since we have no real historical
    # track to report one from.
    timestamp: str | None
    note: str


def lookup_vessel_position(vessel: RosterVessel, *, timeout_s: float = 5.0) -> LiveLookupResult:
    """Look up a roster vessel's live position. Never raises -- any failure
    mode (missing config, network error, no coverage) degrades to the
    vessel's known home port with an explanatory status/note instead.
    """
    api_key = os.environ.get(VESSELAPI_KEY_ENV)
    if not api_key:
        return _fallback(
            vessel,
            status=STATUS_NOT_CONNECTED,
            note=f"{VESSELAPI_KEY_ENV} is not configured (see .env.example)",
        )
    if not vessel.imo:
        return _fallback(
            vessel,
            status=STATUS_NOT_CONNECTED,
            note="No verified IMO number on file for this vessel",
        )

    cached = _get_cached(vessel.imo)
    if cached is not None:
        return cached

    try:
        response = httpx.get(
            f"{VESSELAPI_BASE_URL}/vessel/{vessel.imo}/position",
            params={"filter.idType": "imo"},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout_s,
        )
    except httpx.HTTPError as exc:
        return _fallback(vessel, status=STATUS_NOT_CONNECTED, note=f"AIS lookup request failed: {exc}")

    _warn_if_quota_low(response)

    if response.status_code == 404:
        # A 404 for a roster vessel with a verified IMO means "no position
        # within VesselAPI's lookback window" -- i.e. genuinely out of
        # terrestrial AIS range, not "vessel doesn't exist".
        result = _fallback(vessel, status=STATUS_BEYOND_RANGE, note="No terrestrial AIS position within range")
        _set_cached(vessel.imo, result)
        return result

    if response.status_code != 200:
        return _fallback(vessel, status=STATUS_NOT_CONNECTED, note=f"AIS provider returned HTTP {response.status_code}")

    data = response.json()
    lon, lat = data.get("longitude"), data.get("latitude")
    if lon is None or lat is None:
        result = _fallback(vessel, status=STATUS_BEYOND_RANGE, note="AIS provider response had no position fields")
        _set_cached(vessel.imo, result)
        return result

    result = LiveLookupResult(
        status=STATUS_LIVE,
        lon=float(lon),
        lat=float(lat),
        timestamp=data.get("timestamp"),
        note="Live terrestrial AIS position",
    )
    _set_cached(vessel.imo, result)
    return result


def _get_cached(imo: str) -> LiveLookupResult | None:
    entry = _CACHE.get(imo)
    if entry is None:
        return None
    cached_at, result = entry
    if time.monotonic() - cached_at > CACHE_TTL_SECONDS:
        del _CACHE[imo]
        return None
    return result


def _set_cached(imo: str, result: LiveLookupResult) -> None:
    _CACHE[imo] = (time.monotonic(), result)


def _warn_if_quota_low(response: httpx.Response) -> None:
    remaining = response.headers.get("X-RateLimit-Remaining")
    if remaining is None or remaining == "Unlimited":
        return
    try:
        remaining_count = int(remaining)
    except ValueError:
        return
    if remaining_count < LOW_QUOTA_WARNING_THRESHOLD:
        logger.warning(
            "VesselAPI quota running low: %d calls remaining this period", remaining_count
        )


def _fallback(vessel: RosterVessel, *, status: str, note: str) -> LiveLookupResult:
    lon, lat = vessel.home_port_lonlat
    return LiveLookupResult(
        status=status,
        lon=lon,
        lat=lat,
        timestamp=None,
        note=f"{note} — showing last known position, {vessel.home_port} (home port)",
    )
