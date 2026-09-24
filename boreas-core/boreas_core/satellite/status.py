"""Honest connectivity status for the credential-gated satellite sources.

The rule this module exists to enforce: **never report CONNECTED unless a real
provider request has actually succeeded.** The previous version inferred
"connected" from the presence of environment variables alone, which meant the
UI could claim a live satellite feed while no request had ever left the
process.

A probe therefore does two real things against the Copernicus Data Space
Ecosystem, and reports each separately because they can fail independently:

  1. OAuth2 token (`cdse_auth`) -- proves the configured credentials work.
     Required for imagery pixels via the Sentinel Hub Process API.
  2. STAC metadata search (`stac`) -- a lightweight observation query for the
     mission area of interest, returning a real product id, acquisition time
     and footprint. This is the observation provenance the UI shows.

States:
  CONNECTED         a real request succeeded this probe
  NOT_CONFIGURED    required credentials are absent
  CONNECTION_ERROR  credentials exist but the provider request failed
  DEMO              no real provider request is possible; the application is
                    using synthetic observation data and says so

Probe results are cached, because both the status endpoint and the map layer
poll this, and CDSE's STAC search takes tens of seconds.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from . import stac
from .cdse_auth import CdseAuthError, get_cdse_token

logger = logging.getLogger(__name__)

# CDSE STAC search is slow (routinely 15-20s for a polar bbox), so the probe
# must allow more than the per-call default or it will report a false
# CONNECTION_ERROR purely on timeout.
STAC_PROBE_TIMEOUT_S = 40.0
TOKEN_PROBE_TIMEOUT_S = 10.0

SUCCESS_TTL_SECONDS = 900.0  # 15 min -- these products do not update faster
FAILURE_TTL_SECONDS = 60.0  # retry failures sooner than successes

STATE_CONNECTED = "CONNECTED"
STATE_NOT_CONFIGURED = "NOT_CONFIGURED"
STATE_CONNECTION_ERROR = "CONNECTION_ERROR"
STATE_DEMO = "DEMO"

# Default observation area: the Bharati/Larsemann Hills approach, matching the
# bbox sentinel_hub.py already renders (see KNOWN_LIMITATIONS 1.2 -- a fixed
# AOI is a documented prototype limitation, not a new one introduced here).
DEFAULT_AOI = (74.0, -70.5, 78.5, -68.3)

CDSE_SOURCES = ("sentinel-1", "sentinel-2")
COLLECTIONS = {"sentinel-1": stac.S1_GRD_COLLECTION, "sentinel-2": stac.S2_L2A_COLLECTION}


@dataclass(frozen=True)
class Observation:
    """Provenance for one real satellite observation."""

    product_id: str
    acquired_at: str
    bbox: list[float]
    collection: str
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SourceStatus:
    source_id: str
    state: str
    reason: str
    credentials_configured: bool
    provider: str = "Copernicus Data Space Ecosystem"
    # Set only when a real request succeeded.
    checked_at: str | None = None
    observation: Observation | None = None
    # Whether imagery pixels (not just metadata) can be requested.
    imagery_available: bool = False

    @property
    def connected(self) -> bool:
        """Kept so existing callers that only asked "is this live?" keep
        working -- and it is now only true when a request really succeeded."""
        return self.state == STATE_CONNECTED


# source_id -> (cached_at_monotonic, ttl, SourceStatus)
_CACHE: dict[str, tuple[float, float, SourceStatus]] = {}


def _credentials_configured() -> bool:
    return bool(os.environ.get("CDSE_CLIENT_ID") and os.environ.get("CDSE_CLIENT_SECRET"))


def _probe_cdse_source(source_id: str, aoi: tuple[float, float, float, float]) -> SourceStatus:
    now_iso = datetime.now(UTC).isoformat()

    if not _credentials_configured():
        return SourceStatus(
            source_id=source_id,
            state=STATE_DEMO,
            reason=(
                "CDSE_CLIENT_ID / CDSE_CLIENT_SECRET not configured — satellite observation data "
                "is simulated for this prototype."
            ),
            credentials_configured=False,
            checked_at=now_iso,
        )

    # 1. Do the credentials actually work?
    try:
        get_cdse_token(timeout_s=TOKEN_PROBE_TIMEOUT_S)
    except CdseAuthError as exc:
        return SourceStatus(
            source_id=source_id,
            state=STATE_CONNECTION_ERROR,
            reason=f"CDSE credentials configured but authentication failed: {exc}",
            credentials_configured=True,
            checked_at=now_iso,
        )

    # 2. Is there a real observation over the AOI? Metadata only -- no pixels.
    try:
        if source_id == "sentinel-1":
            scene = stac.discover_latest_sentinel1_scene(aoi, timeout_s=STAC_PROBE_TIMEOUT_S)
            observation = (
                Observation(
                    product_id=scene.item_id,
                    acquired_at=scene.datetime,
                    bbox=list(scene.bbox),
                    collection=COLLECTIONS[source_id],
                    extra={
                        "instrument_mode": scene.instrument_mode,
                        "polarizations": scene.polarizations,
                    },
                )
                if scene
                else None
            )
        else:
            scene = stac.discover_best_sentinel2_scene(aoi, timeout_s=STAC_PROBE_TIMEOUT_S)
            observation = (
                Observation(
                    product_id=scene.item_id,
                    acquired_at=scene.datetime,
                    bbox=list(scene.bbox),
                    collection=COLLECTIONS[source_id],
                    extra={"cloud_cover": scene.cloud_cover, "tile_id": scene.tile_id},
                )
                if scene
                else None
            )
    except Exception as exc:  # network/parse failures must degrade, never 500
        logger.warning("CDSE STAC probe failed for %s: %s", source_id, exc)
        return SourceStatus(
            source_id=source_id,
            state=STATE_CONNECTION_ERROR,
            reason=f"Authenticated, but the observation search failed: {exc}",
            credentials_configured=True,
            checked_at=now_iso,
        )

    if observation is None:
        # Authentication worked, the provider answered, but has nothing here.
        # That is a successful request, so it is not an error -- but it is not
        # an observation either, and must not be presented as one.
        return SourceStatus(
            source_id=source_id,
            state=STATE_CONNECTED,
            reason="Authenticated; provider returned no recent scene over the mission area.",
            credentials_configured=True,
            checked_at=now_iso,
            imagery_available=False,
        )

    return SourceStatus(
        source_id=source_id,
        state=STATE_CONNECTED,
        reason="Authenticated; real observation metadata retrieved from CDSE.",
        credentials_configured=True,
        checked_at=now_iso,
        observation=observation,
        imagery_available=True,
    )


def _copernicus_marine_status() -> SourceStatus:
    """Copernicus Marine has no lightweight metadata probe in this codebase --
    the toolbox call downloads a NetCDF -- so no cheap request can prove it is
    live. It therefore never reports CONNECTED.

    Either way the sea-ice field BOREAS actually routes on is the prototype
    forecast engine, not a Marine product, so DEMO is the truthful state for
    what is feeding decisions; the reason line distinguishes whether
    credentials happen to be present.
    """
    now_iso = datetime.now(UTC).isoformat()
    configured = bool(
        os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME")
        and os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD")
    )
    reason = (
        "Credentials present, but no request has been made — the sea-ice field in use is the "
        "prototype forecast, not a Copernicus Marine product."
        if configured
        else "COPERNICUSMARINE_SERVICE_USERNAME / _PASSWORD not configured — the sea-ice field in "
        "use is the prototype forecast."
    )
    return SourceStatus(
        source_id="copernicus-marine",
        state=STATE_DEMO,
        reason=reason,
        credentials_configured=configured,
        provider="Copernicus Marine Service",
        checked_at=now_iso,
    )


def get_source_status(source_id: str, *, aoi=DEFAULT_AOI, force: bool = False) -> SourceStatus:
    cached = _CACHE.get(source_id)
    if cached is not None and not force:
        cached_at, ttl, result = cached
        if time.monotonic() - cached_at < ttl:
            return result

    if source_id in CDSE_SOURCES:
        status = _probe_cdse_source(source_id, aoi)
    elif source_id == "copernicus-marine":
        status = _copernicus_marine_status()
    else:
        return SourceStatus(
            source_id=source_id,
            state=STATE_NOT_CONFIGURED,
            reason=f"Unknown satellite source: {source_id}",
            credentials_configured=False,
        )

    ttl = SUCCESS_TTL_SECONDS if status.state in (STATE_CONNECTED, STATE_DEMO) else FAILURE_TTL_SECONDS
    _CACHE[source_id] = (time.monotonic(), ttl, status)
    return status


def get_all_statuses(*, aoi=DEFAULT_AOI) -> dict[str, SourceStatus]:
    return {
        "sentinel-1": get_source_status("sentinel-1", aoi=aoi),
        "sentinel-2": get_source_status("sentinel-2", aoi=aoi),
        "copernicus-marine": get_source_status("copernicus-marine"),
    }


def _clear_cache_for_tests() -> None:
    _CACHE.clear()
