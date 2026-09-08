"""Real Sentinel-1/Sentinel-2 quicklook imagery via the Copernicus Data
Space Ecosystem's Sentinel Hub Process API.

Endpoint and request shape verified against CDSE's own current
documentation this session (not guessed):
documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html
-- Process API at https://sh.dataspace.copernicus.eu/api/v1/process,
authorized with a CDSE OAuth2 bearer token (see cdse_auth.py).

Bounding box: Prydz Bay / Larsemann Hills sector around Bharati Station
(see boreas_core/vessels/roster.py's checkpoint data) -- a real, meaningful
area for this app rather than an arbitrary patch of ocean. Sentinel-1 has a
~6-12 day repeat cycle and Sentinel-2 ~5 days at this latitude, so neither
guarantees an acquisition on any single day; the request asks for the most
recent scene in the last 14 days (`mosaickingOrder: "mostRecent"`) rather
than a fixed date, which is what "recently updated data" actually means for
a real narrow-swath sensor (unlike MODIS/VIIRS's near-daily global revisit).
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import httpx

from .cdse_auth import CdseAuthError, get_cdse_token

logger = logging.getLogger(__name__)

PROCESS_API_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"

# lon_min, lat_min, lon_max, lat_max
BBOX = (74.0, -70.5, 78.5, -68.3)
LOOKBACK_DAYS = 14
OUTPUT_SIZE = 512

_SENTINEL_1_EVALSCRIPT = """
//VERSION=3
function setup() {
  return { input: ["VV", "VH"], output: { bands: 3 } };
}
function evaluatePixel(sample) {
  let vv = Math.min(1, sample.VV * 8);
  let vh = Math.min(1, sample.VH * 12);
  return [vv, (vv + vh) / 2, vh];
}
"""

_SENTINEL_2_EVALSCRIPT = """
//VERSION=3
function setup() {
  return { input: ["B04", "B03", "B02"], output: { bands: 3 } };
}
function evaluatePixel(sample) {
  return [2.5 * sample.B04, 2.5 * sample.B03, 2.5 * sample.B02];
}
"""

_SOURCE_CONFIG = {
    "sentinel-1": {"type": "S1GRD", "evalscript": _SENTINEL_1_EVALSCRIPT},
    "sentinel-2": {"type": "S2L2A", "evalscript": _SENTINEL_2_EVALSCRIPT},
}


@dataclass
class QuicklookResult:
    available: bool
    image_bytes: bytes | None
    content_type: str
    reason: str
    # Raw upstream diagnostic detail -- CDSE token-exchange error dict (see
    # CdseAuthError.debug_dict) or {"upstream_status", "upstream_body",
    # "request_body"} from a failed Process API call -- so a caller can
    # tell "bad credentials" from "no scene in range" from "auth scope
    # issue" instead of only a flattened message. None on success.
    debug: dict | None = None


def fetch_sentinel_quicklook(source_id: Literal["sentinel-1", "sentinel-2"], *, timeout_s: float = 30.0) -> QuicklookResult:
    """Never raises -- any failure (missing/invalid credentials, network
    error, no scene found) degrades to `available=False` with a reason.
    """
    config = _SOURCE_CONFIG.get(source_id)
    if config is None:
        return QuicklookResult(available=False, image_bytes=None, content_type="", reason=f"Unknown source {source_id}")

    try:
        token = get_cdse_token()
    except CdseAuthError as exc:
        return QuicklookResult(available=False, image_bytes=None, content_type="", reason=str(exc), debug=exc.debug_dict())

    now = datetime.now(UTC)
    start = now - timedelta(days=LOOKBACK_DAYS)
    lon_min, lat_min, lon_max, lat_max = BBOX

    request_body = {
        "input": {
            "bounds": {"bbox": [lon_min, lat_min, lon_max, lat_max]},
            "data": [
                {
                    "type": config["type"],
                    "dataFilter": {
                        "timeRange": {"from": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "to": now.strftime("%Y-%m-%dT%H:%M:%SZ")},
                        "mosaickingOrder": "mostRecent",
                    },
                }
            ],
        },
        "output": {"width": OUTPUT_SIZE, "height": OUTPUT_SIZE, "responses": [{"identifier": "default", "format": {"type": "image/png"}}]},
        "evalscript": config["evalscript"],
    }

    try:
        response = httpx.post(
            PROCESS_API_URL,
            json=request_body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_s,
        )
    except httpx.HTTPError as exc:
        logger.warning("Sentinel Hub request failed (network) for %s: %s", source_id, exc)
        return QuicklookResult(
            available=False,
            image_bytes=None,
            content_type="",
            reason=f"Sentinel Hub request failed: {exc}",
            debug={"exception_type": type(exc).__name__, "exception": str(exc)},
        )

    if response.status_code != 200:
        # Not truncated -- Sentinel Hub's error body is short JSON
        # ({"error": {"status": ..., "reason": ..., "message": ...}}) and
        # is exactly the "real cause" (bad creds vs. no scene vs. scope
        # issue) this field exists to surface.
        logger.warning("Sentinel Hub returned HTTP %s for %s: %s", response.status_code, source_id, response.text)
        return QuicklookResult(
            available=False,
            image_bytes=None,
            content_type="",
            reason=f"Sentinel Hub returned HTTP {response.status_code}: {response.text}",
            debug={
                "upstream_status": response.status_code,
                "upstream_body": response.text,
                "request_bbox": list(BBOX),
                "request_type": config["type"],
                "request_time_range": {"from": start.isoformat(), "to": now.isoformat()},
            },
        )

    return QuicklookResult(available=True, image_bytes=response.content, content_type="image/png", reason="OK")
