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
from . import stac

logger = logging.getLogger(__name__)

PROCESS_API_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"

# lon_min, lat_min, lon_max, lat_max
BBOX = (74.0, -70.5, 78.5, -68.3)
LOOKBACK_DAYS = 14
OUTPUT_SIZE = 512

_SENTINEL_2_EVALSCRIPT = """//VERSION=3
function setup() {
  return { input: ["B04", "B03", "B02", "dataMask"], output: { bands: 4 } };
}
function evaluatePixel(sample) {
  return [2.5 * sample.B04, 2.5 * sample.B03, 2.5 * sample.B02, sample.dataMask * 255];
}
"""

_SOURCE_CONFIG = {
    "sentinel-1": {"type": "S1GRD"},
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
    metadata: dict | None = None


def fetch_sentinel_quicklook(source_id: Literal["sentinel-1", "sentinel-2"], *, timeout_s: float = 45.0) -> QuicklookResult:
    """Never raises -- any failure (missing/invalid credentials, network
    error, no scene found) degrades to `available=False` with a reason.
    """
    config = _SOURCE_CONFIG.get(source_id)
    if config is None:
        return QuicklookResult(available=False, image_bytes=None, content_type="", reason=f"Unknown source {source_id}")

    try:
        token = get_cdse_token()
    except CdseAuthError as exc:
        return QuicklookResult(
            available=False,
            image_bytes=None,
            content_type="",
            reason=f"CDSE authentication failed: {exc}",
            debug=exc.debug_dict(),
        )

    now = datetime.now(UTC)
    start = now - timedelta(days=LOOKBACK_DAYS)
    lon_min, lat_min, lon_max, lat_max = BBOX
    render_bbox = list(BBOX)

    data_filter: dict[str, Any] = {
        "timeRange": {
            "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }
    selected_metadata: dict | None = None

    if source_id == "sentinel-1":
        scene = stac.discover_latest_sentinel1_scene(BBOX, lookback_days=LOOKBACK_DAYS, timeout_s=25.0)
        if scene is None:
            return QuicklookResult(
                available=False,
                image_bytes=None,
                content_type="",
                reason="No Sentinel-1 scene found via CDSE STAC in range",
                debug={"bbox": list(BBOX), "lookback_days": LOOKBACK_DAYS},
            )

        try:
            pol_cfg = stac.resolve_polarization_config(scene)
        except ValueError as exc:
            return QuicklookResult(
                available=False,
                image_bytes=None,
                content_type="",
                reason=str(exc),
                debug={
                    "item_id": scene.item_id,
                    "polarizations": scene.polarizations,
                    "instrument_mode": scene.instrument_mode,
                },
            )

        data_filter["acquisitionMode"] = pol_cfg.acquisition_mode
        data_filter["polarization"] = pol_cfg.polarization_mode
        evalscript = pol_cfg.evalscript
        selected_metadata = {
            "scene_id": scene.item_id,
            "datetime": scene.datetime,
            "polarization": pol_cfg.polarization_mode,
            "bands": pol_cfg.bands,
            "bbox": list(BBOX),
        }
    elif source_id == "sentinel-2":
        s2_scene = stac.discover_best_sentinel2_scene(BBOX, lookback_days=LOOKBACK_DAYS, max_cloud_cover=50.0, timeout_s=25.0)
        if s2_scene is None:
            return QuicklookResult(
                available=False,
                image_bytes=None,
                content_type="",
                reason="No Sentinel-2 scene found via CDSE STAC in range",
                debug={"bbox": list(BBOX), "lookback_days": LOOKBACK_DAYS},
            )

        # Narrow timeRange around the selected acquisition date/time so Sentinel Hub renders
        # the specific clear acquisition rather than compositing unrelated cloudy scenes.
        try:
            scene_dt = datetime.fromisoformat(s2_scene.datetime.replace("Z", "+00:00"))
            dt_from = (scene_dt - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
            dt_to = (scene_dt + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            dt_from = start.strftime("%Y-%m-%dT%H:%M:%SZ")
            dt_to = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        data_filter["timeRange"] = {"from": dt_from, "to": dt_to}
        data_filter["mosaickingOrder"] = "leastCC"
        evalscript = config["evalscript"]
        if s2_scene.bbox and len(s2_scene.bbox) == 4:
            render_bbox = list(s2_scene.bbox)

        selected_metadata = {
            "scene_id": s2_scene.item_id,
            "datetime": s2_scene.datetime,
            "cloud_cover": s2_scene.cloud_cover,
            "tile_id": s2_scene.tile_id,
            "bbox": render_bbox,
            "scene_bbox": list(s2_scene.bbox),
        }
        logger.info(
            "Selected Sentinel-2 scene %s (cloud_cover=%.1f%%, dt=%s, bbox=%s) for Processing API request",
            s2_scene.item_id, s2_scene.cloud_cover, s2_scene.datetime, render_bbox
        )
    else:
        evalscript = config["evalscript"]

    request_body = {
        "input": {
            "bounds": {"bbox": render_bbox},
            "data": [
                {
                    "type": config["type"],
                    "dataFilter": data_filter,
                }
            ],
        },
        "output": {"width": OUTPUT_SIZE, "height": OUTPUT_SIZE, "responses": [{"identifier": "default", "format": {"type": "image/png"}}]},
        "evalscript": evalscript,
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
                "request_bbox": render_bbox,
                "request_type": config["type"],
                "request_time_range": {"from": start.isoformat(), "to": now.isoformat()},
            },
        )

    return QuicklookResult(
        available=True,
        image_bytes=response.content,
        content_type="image/png",
        reason="OK",
        metadata=selected_metadata,
    )
