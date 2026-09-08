"""Orchestrates real satellite quicklook fetches for the frontend's
GET /satellite/{source_id}/quicklook endpoint, with a short in-memory cache
so every tile render (and every browser polling this endpoint) doesn't
re-trigger a real upstream fetch -- these products don't update faster than
daily/6-hourly anyway, and Sentinel-1/2 quicklooks in particular are
expensive Process API calls worth reusing across requests.
"""

import time
from dataclasses import dataclass

from . import copernicus_marine_fetch, sentinel_hub

CACHE_TTL_SECONDS = 1800.0  # 30 minutes


@dataclass
class Quicklook:
    available: bool
    image_bytes: bytes | None
    content_type: str
    reason: str
    debug: dict | None = None


# source_id -> (cached_at_monotonic, Quicklook)
_CACHE: dict[str, tuple[float, Quicklook]] = {}


def get_quicklook(source_id: str) -> Quicklook:
    cached = _CACHE.get(source_id)
    if cached is not None:
        cached_at, result = cached
        if time.monotonic() - cached_at < CACHE_TTL_SECONDS:
            return result

    result = _fetch(source_id)
    # Only cache genuine successes -- a transient failure (network blip,
    # momentary auth hiccup) should be retried on the next request, not
    # stuck showing "NOT CONNECTED" for the full TTL.
    if result.available:
        _CACHE[source_id] = (time.monotonic(), result)
    return result


def _fetch(source_id: str) -> Quicklook:
    if source_id in ("sentinel-1", "sentinel-2"):
        raw = sentinel_hub.fetch_sentinel_quicklook(source_id)
        return Quicklook(
            available=raw.available, image_bytes=raw.image_bytes, content_type=raw.content_type, reason=raw.reason, debug=raw.debug
        )

    if source_id == "copernicus-marine":
        raw = copernicus_marine_fetch.fetch_sea_ice_concentration_raster()
        return Quicklook(
            available=raw.available, image_bytes=raw.image_bytes, content_type=raw.content_type, reason=raw.reason, debug=raw.debug
        )

    return Quicklook(available=False, image_bytes=None, content_type="", reason=f"Unknown satellite source: {source_id}")


def _clear_cache_for_tests() -> None:
    _CACHE.clear()
