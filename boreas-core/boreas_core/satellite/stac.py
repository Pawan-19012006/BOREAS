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
S2_L2A_COLLECTION = "sentinel-2-l2a"

# Bharati Station / Larsemann Hills operational coordinates (lon, lat)
BHARATI_STATION_COORDS = (76.19, -69.41)


def compute_bbox_overlap_area(
    bbox1: tuple[float, float, float, float] | list[float],
    bbox2: tuple[float, float, float, float] | list[float],
) -> float:
    """Computes the 2D intersection area (in deg^2) between two [min_lon, min_lat, max_lon, max_lat] bounding boxes."""
    if len(bbox1) < 4 or len(bbox2) < 4:
        return 0.0
    dx = max(0.0, min(bbox1[2], bbox2[2]) - max(bbox1[0], bbox2[0]))
    dy = max(0.0, min(bbox1[3], bbox2[3]) - max(bbox1[1], bbox2[1]))
    return dx * dy



@dataclass(frozen=True)
class Sentinel2Scene:
    item_id: str
    datetime: str
    cloud_cover: float
    bbox: list[float]
    geometry: dict[str, Any]
    tile_id: str | None = None
    nodata_percentage: float | None = None


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


def _parse_iso_timestamp(dt_str: str) -> float:
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def discover_best_sentinel2_scene(
    bbox: tuple[float, float, float, float],
    lookback_days: int = 14,
    max_cloud_cover: float = 50.0,
    *,
    timeout_s: float = 25.0,
    client: httpx.Client | None = None,
) -> Sentinel2Scene | None:
    """Discovers the best Sentinel-2 L2A scene matching the bounding box
    and lookback window via CDSE STAC search.

    Filtering & Selection Rules:
    - Queries sentinel-2-l2a collection.
    - Inspects eo:cloud_cover (or cloud_cover).
    - Ignores boundary slivers where nodata percentage >= 80% if other scenes exist.
    - Prefers scenes with cloud cover <= max_cloud_cover.
    - Among qualifying scenes, selects the lowest cloud-cover scene.
    - Uses acquisition datetime as secondary criterion (more recent preferred if cloud cover is equal).
    - If no scene meets max_cloud_cover, falls back to the lowest-cloud scene available rather than failing outright.
    - If all scenes lack cloud metadata, falls back to the most recent scene.
    - Returns None if no features are returned or on network/HTTP error.
    """
    now = datetime.now(UTC)
    start = now - timedelta(days=lookback_days)
    lon_min, lat_min, lon_max, lat_max = bbox

    payload = {
        "collections": [S2_L2A_COLLECTION],
        "bbox": [lon_min, lat_min, lon_max, lat_max],
        "datetime": f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{now.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "limit": 50,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }

    try:
        if client is not None:
            resp = client.post(CDSE_STAC_SEARCH_URL, json=payload, timeout=timeout_s)
        else:
            with httpx.Client(timeout=timeout_s) as http:
                resp = http.post(CDSE_STAC_SEARCH_URL, json=payload)
    except httpx.HTTPError as exc:
        logger.warning("CDSE STAC S2 search failed (network): %s", exc)
        return None

    if resp.status_code != 200:
        logger.warning("CDSE STAC S2 search returned HTTP %s: %s", resp.status_code, resp.text)
        return None

    data = resp.json()
    features = data.get("features", [])
    if not features:
        logger.info("CDSE STAC search found no Sentinel-2 scenes in bbox=%s, lookback=%sd", bbox, lookback_days)
        return None

    # Parse candidate scenes and evaluate geographic overlap
    target_area = max(0.0, (lon_max - lon_min) * (lat_max - lat_min))
    operational_in_target = (lon_min <= BHARATI_STATION_COORDS[0] <= lon_max and lat_min <= BHARATI_STATION_COORDS[1] <= lat_max)

    candidates = []
    for f in features:
        props = f.get("properties", {})
        raw_cc = props.get("eo:cloud_cover")
        if raw_cc is None:
            raw_cc = props.get("cloud_cover")

        cc = float(raw_cc) if raw_cc is not None else None
        dt = props.get("datetime", "")
        item_id = f.get("id", "")
        tile_id = props.get("grid:code") or props.get("s2:mgrs_tile")
        stats = props.get("statistics", {})
        nodata = stats.get("nodata")
        nodata_val = float(nodata) if nodata is not None else None

        f_bbox = f.get("bbox") or []
        ov_area = compute_bbox_overlap_area(f_bbox, bbox) if len(f_bbox) >= 4 else 0.0
        f_area = max(0.0, (f_bbox[2] - f_bbox[0]) * (f_bbox[3] - f_bbox[1])) if len(f_bbox) >= 4 else 0.0
        aoi_overlap_ratio = (ov_area / target_area) if target_area > 0 else 0.0
        scene_overlap_ratio = (ov_area / f_area) if f_area > 0 else 0.0

        contains_operational = (
            operational_in_target
            and len(f_bbox) >= 4
            and (f_bbox[0] <= BHARATI_STATION_COORDS[0] <= f_bbox[2])
            and (f_bbox[1] <= BHARATI_STATION_COORDS[1] <= f_bbox[3])
        )
        is_boundary_sliver = (aoi_overlap_ratio < 0.05 and scene_overlap_ratio < 0.15)
        has_substantial_overlap = (contains_operational or aoi_overlap_ratio >= 0.10 or scene_overlap_ratio >= 0.40)

        candidates.append({
            "feature": f,
            "id": item_id,
            "datetime": dt,
            "cloud_cover": cc,
            "nodata": nodata_val,
            "tile_id": tile_id,
            "timestamp": _parse_iso_timestamp(dt),
            "bbox": f_bbox,
            "overlap_area": ov_area,
            "aoi_overlap_ratio": aoi_overlap_ratio,
            "scene_overlap_ratio": scene_overlap_ratio,
            "contains_operational": contains_operational,
            "is_boundary_sliver": is_boundary_sliver,
            "has_substantial_overlap": has_substantial_overlap,
        })

    # 1. Filter out scenes that are nearly 100% nodata boundary slivers
    valid_data_scenes = [
        c for c in candidates
        if c["nodata"] is None or c["nodata"] < 80.0
    ]
    pool = valid_data_scenes if valid_data_scenes else candidates

    # 2. Reject scenes with only a tiny boundary intersection if non-sliver scenes exist
    non_slivers = [c for c in pool if not c["is_boundary_sliver"]]
    active_pool = non_slivers if non_slivers else pool

    # 3. Prefer scenes with substantial overlap with the operational AOI
    substantial = [c for c in active_pool if c["has_substantial_overlap"]]
    candidate_pool = substantial if substantial else active_pool

    # 4. Multi-tier ranking:
    # Prioritizes:
    #   1. Meaningful spatial overlap (covering operational center / higher overlap)
    #   2. Acceptable cloud cover (<= max_cloud_cover)
    #   3. Lower cloud cover
    #   4. Acquisition recency
    def _rank_key(c: dict) -> tuple:
        op_rank = 0 if c["contains_operational"] else 1
        cc_rank = c["cloud_cover"] if c["cloud_cover"] is not None else 1000.0
        recency_rank = -c["timestamp"]
        ov_rank = -c["overlap_area"]
        return (op_rank, cc_rank, recency_rank, ov_rank)

    scenes_with_cc = [c for c in candidate_pool if c["cloud_cover"] is not None]
    qualifying = [c for c in scenes_with_cc if c["cloud_cover"] <= max_cloud_cover]

    if qualifying:
        selected = sorted(qualifying, key=_rank_key)[0]
        logger.info(
            "Selected qualifying Sentinel-2 scene %s: cloud=%.1f%% (threshold=%.1f%%) operational=%s overlap=%.2f dt=%s",
            selected["id"], selected["cloud_cover"], max_cloud_cover, selected["contains_operational"], selected["overlap_area"], selected["datetime"]
        )
    elif scenes_with_cc:
        selected = sorted(scenes_with_cc, key=_rank_key)[0]
        logger.warning(
            "No Sentinel-2 scene met threshold %.1f%%; falling back to best spatial/cloud scene %s: cloud=%.1f%% dt=%s",
            max_cloud_cover, selected["id"], selected["cloud_cover"], selected["datetime"]
        )
    else:
        selected = sorted(candidate_pool, key=lambda c: (0 if c["contains_operational"] else 1, -c["overlap_area"], -c["timestamp"]))[0]
        logger.warning(
            "Sentinel-2 scenes lack cloud metadata; falling back to most recent spatial scene %s: dt=%s",
            selected["id"], selected["datetime"]
        )

    f = selected["feature"]
    return Sentinel2Scene(
        item_id=selected["id"],
        datetime=selected["datetime"],
        cloud_cover=selected["cloud_cover"] if selected["cloud_cover"] is not None else -1.0,
        bbox=f.get("bbox", []),
        geometry=f.get("geometry", {}),
        tile_id=selected["tile_id"],
        nodata_percentage=selected["nodata"],
    )
