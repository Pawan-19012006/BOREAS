"""CDSE STAC API client for Sentinel-1 scene discovery and polarization metadata.

Queries the Copernicus Data Space Ecosystem STAC endpoint
(https://stac.dataspace.copernicus.eu/v1/) to discover real Sentinel-1 GRD acquisitions,
inspect their metadata (s1:polarization / sar:polarizations, sar:instrument_mode,
datetime, bbox, geometry, item ID), and determine the appropriate polarization configuration
and evalscript for the Sentinel Hub Processing API.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CDSE_STAC_SEARCH_URL = "https://stac.dataspace.copernicus.eu/v1/search"
S1_GRD_COLLECTION = "sentinel-1-grd"


@dataclass(frozen=True)
class Sentinel1Scene:
    item_id: str
    datetime: str
    instrument_mode: str
    polarizations: list[str]
    bbox: list[float]
    geometry: dict[str, Any]


@dataclass(frozen=True)
class PolarizationConfig:
    polarization_mode: str  # "DH", "DV", "SH", "SV"
    acquisition_mode: str   # "EW", "IW", "SM"
    bands: list[str]        # ["HH", "HV"] or ["VV", "VH"] or ["HH"] or ["VV"]
    evalscript: str


def build_s1_evalscript(bands: list[str]) -> str:
    """Builds a Sentinel Hub v3 evalscript for the given polarization bands.
    Dual-pol generates a false-color composite; single-pol generates a grayscale RGB image.
    """
    if len(bands) == 2:
        co_pol, cross_pol = bands[0], bands[1]
        return f"""//VERSION=3
function setup() {{
  return {{ input: ["{co_pol}", "{cross_pol}"], output: {{ bands: 3 }} }};
}}
function evaluatePixel(sample) {{
  let co = Math.min(1, sample.{co_pol} * 8);
  let cross = Math.min(1, sample.{cross_pol} * 12);
  return [co, (co + cross) / 2, cross];
}}
"""
    elif len(bands) == 1:
        pol = bands[0]
        return f"""//VERSION=3
function setup() {{
  return {{ input: ["{pol}"], output: {{ bands: 3 }} }};
}}
function evaluatePixel(sample) {{
  let val = Math.min(1, sample.{pol} * 8);
  return [val, val, val];
}}
"""
    raise ValueError(f"Expected 1 or 2 bands for Sentinel-1 evalscript, got: {bands}")


def resolve_polarization_config(scene: Sentinel1Scene) -> PolarizationConfig:
    """Resolves the Sentinel Hub Processing API polarization filter and evalscript
    based on the scene's polarizations and instrument mode.

    Rules:
    - HH + HV -> Dual Horizontal ('DH'), bands ['HH', 'HV']
    - VV + VH -> Dual Vertical ('DV'), bands ['VV', 'VH']
    - Single HH -> Single Horizontal ('SH'), bands ['HH']
    - Single VV -> Single Vertical ('SV'), bands ['VV']
    - Anything else / empty -> raises ValueError with explicit reason
    """
    pols = [p.upper().strip() for p in scene.polarizations if p and isinstance(p, str)]
    mode = scene.instrument_mode.upper().strip() if scene.instrument_mode else "EW"

    if "HH" in pols and "HV" in pols:
        return PolarizationConfig(
            polarization_mode="DH",
            acquisition_mode=mode,
            bands=["HH", "HV"],
            evalscript=build_s1_evalscript(["HH", "HV"]),
        )
    if "VV" in pols and "VH" in pols:
        return PolarizationConfig(
            polarization_mode="DV",
            acquisition_mode=mode,
            bands=["VV", "VH"],
            evalscript=build_s1_evalscript(["VV", "VH"]),
        )
    if "HH" in pols:
        return PolarizationConfig(
            polarization_mode="SH",
            acquisition_mode=mode,
            bands=["HH"],
            evalscript=build_s1_evalscript(["HH"]),
        )
    if "VV" in pols:
        return PolarizationConfig(
            polarization_mode="SV",
            acquisition_mode=mode,
            bands=["VV"],
            evalscript=build_s1_evalscript(["VV"]),
        )

    raise ValueError(f"Unsupported or missing Sentinel-1 polarization metadata: {scene.polarizations}")


def discover_latest_sentinel1_scene(
    bbox: tuple[float, float, float, float],
    lookback_days: int = 14,
    *,
    timeout_s: float = 15.0,
    client: httpx.Client | None = None,
) -> Sentinel1Scene | None:
    """Discovers the most recent Sentinel-1 GRD scene matching the bounding box
    and lookback window via CDSE STAC search. Returns None if no scene is found or on network error.
    """
    now = datetime.now(UTC)
    start = now - timedelta(days=lookback_days)
    lon_min, lat_min, lon_max, lat_max = bbox

    payload = {
        "collections": [S1_GRD_COLLECTION],
        "bbox": [lon_min, lat_min, lon_max, lat_max],
        "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "limit": 5,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }

    try:
        if client is not None:
            resp = client.post(CDSE_STAC_SEARCH_URL, json=payload, timeout=timeout_s)
        else:
            with httpx.Client(timeout=timeout_s) as http:
                resp = http.post(CDSE_STAC_SEARCH_URL, json=payload)
    except httpx.HTTPError as exc:
        logger.warning("CDSE STAC search failed (network): %s", exc)
        return None

    if resp.status_code != 200:
        logger.warning("CDSE STAC search returned HTTP %s: %s", resp.status_code, resp.text)
        return None

    data = resp.json()
    features = data.get("features", [])
    if not features:
        logger.info("CDSE STAC search found no Sentinel-1 scenes in bbox=%s, lookback=%sd", bbox, lookback_days)
        return None

    first = features[0]
    props = first.get("properties", {})
    item_id = first.get("id", "")
    dt = props.get("datetime", "")
    mode = props.get("sar:instrument_mode") or "EW"

    # Support s1:polarization, sar:polarizations, or polarization property
    raw_pols = props.get("sar:polarizations") or props.get("s1:polarization") or props.get("polarization") or []
    if isinstance(raw_pols, str):
        raw_pols = [raw_pols]

    return Sentinel1Scene(
        item_id=item_id,
        datetime=dt,
        instrument_mode=mode,
        polarizations=list(raw_pols),
        bbox=first.get("bbox", []),
        geometry=first.get("geometry", {}),
    )
