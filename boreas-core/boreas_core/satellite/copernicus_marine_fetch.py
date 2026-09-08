"""Real Copernicus Marine Antarctic sea-ice-concentration fetch + rasterization.

Dataset verified this session against data.marine.copernicus.eu's own
product page (not guessed): product SEAICE_GLO_SEAICE_L4_NRT_OBSERVATIONS_011_001
("Global Ocean - Arctic and Antarctic - Sea Ice Concentration, Edge, Type
and Drift (OSI-SAF)"), dataset id
`osisaf_obs-si_glo_phy-sic-south_nrt_amsr2_l4_P1D-m` (AMSR2-based, daily,
Southern-hemisphere) -- coverage confirmed live through 2026-09-06 as of
this session.

Authentication: Copernicus Marine migrated its auth system in September
2026 to a new host (auth.marine.copernicus.eu); per the Toolbox's own
current docs, `copernicusmarine>=2.0.0` (pinned in pyproject.toml) handles
this transparently via the same COPERNICUSMARINE_SERVICE_USERNAME/PASSWORD
env vars this codebase already used pre-migration -- no code change needed
here for that migration itself.

The exact NetCDF variable/coordinate names for this dataset were not
independently confirmed against a live call in this sandbox (no real
credentials configured here) -- rather than hardcode a guessed name and
risk silently mis-plotting (as happened once already with the ensemble
heatmap's north/south axis), this module searches for plausible names and
determines row orientation from the dataset's own latitude coordinate
values at fetch time, and fails closed (available=False) with a clear
reason if it can't confidently identify either.
"""

import io
import logging
import traceback
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

DATASET_ID = "osisaf_obs-si_glo_phy-sic-south_nrt_amsr2_l4_P1D-m"

# Same Prydz Bay / Bharati Station sector as sentinel_hub.py, widened a bit
# since this product's native resolution (~10km) is much coarser than
# Sentinel-1/2 -- a tight box would only cover a handful of pixels.
BBOX = {"minimum_longitude": 60.0, "maximum_longitude": 95.0, "minimum_latitude": -72.0, "maximum_latitude": -60.0}

_LAT_NAME_CANDIDATES = ("lat", "latitude")
_LON_NAME_CANDIDATES = ("lon", "longitude")
_CONCENTRATION_NAME_HINTS = ("ice_conc", "siconc", "concentration")


@dataclass
class RasterResult:
    available: bool
    image_bytes: bytes | None
    content_type: str
    acquired_at: str | None
    reason: str
    # Raw upstream diagnostic detail -- exception type/message and a capped
    # traceback for a copernicusmarine failure, or the actual dataset
    # coords/vars seen when field-name detection fails -- so a caller can
    # tell "bad credentials" from "dataset shape changed" instead of only a
    # flattened message. None on success.
    debug: dict | None = None


def _exception_debug(exc: Exception, *, traceback_limit: int = 2000) -> dict:
    return {
        "exception_type": type(exc).__name__,
        "exception": str(exc),
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-traceback_limit:],
    }


def _find_name(candidates: dict, hints: tuple[str, ...]) -> str | None:
    names = list(candidates)
    for hint in hints:
        for name in names:
            if name.lower() == hint:
                return name
    for hint in hints:
        for name in names:
            if hint in name.lower():
                return name
    return None


def fetch_sea_ice_concentration_raster(*, timeout_s: float = 60.0) -> RasterResult:
    """Never raises -- any failure (missing/invalid credentials, network
    error, unrecognized dataset shape) degrades to `available=False` with a
    reason, matching every other satellite source's honesty contract.
    """
    try:
        import copernicusmarine
    except ImportError as exc:
        return RasterResult(
            available=False,
            image_bytes=None,
            content_type="",
            acquired_at=None,
            reason=f"copernicusmarine not installed: {exc}",
            debug=_exception_debug(exc),
        )

    try:
        dataset = copernicusmarine.open_dataset(dataset_id=DATASET_ID, **BBOX)
    except Exception as exc:  # noqa: BLE001 -- third-party client, many failure modes (auth, network, dataset moved)
        logger.warning("Copernicus Marine fetch failed: %s", exc, exc_info=True)
        return RasterResult(
            available=False,
            image_bytes=None,
            content_type="",
            acquired_at=None,
            reason=f"Copernicus Marine fetch failed: {exc}",
            debug=_exception_debug(exc),
        )

    lat_name = _find_name(dict(dataset.coords), _LAT_NAME_CANDIDATES)
    lon_name = _find_name(dict(dataset.coords), _LON_NAME_CANDIDATES)
    var_name = _find_name(dict(dataset.data_vars), _CONCENTRATION_NAME_HINTS)

    if not lat_name or not lon_name or not var_name:
        return RasterResult(
            available=False,
            image_bytes=None,
            content_type="",
            acquired_at=None,
            reason=(
                f"Could not identify lat/lon/concentration fields in dataset "
                f"(coords: {list(dataset.coords)}, vars: {list(dataset.data_vars)})"
            ),
            debug={"coords": list(dataset.coords), "data_vars": list(dataset.data_vars)},
        )

    try:
        data_array = dataset[var_name]
        if "time" in data_array.dims:
            data_array = data_array.isel(time=-1)
            acquired_at = str(dataset["time"].values[-1]) if "time" in dataset.coords else None
        else:
            acquired_at = None

        data_array = data_array.transpose(lat_name, lon_name)
        values = np.asarray(data_array.values, dtype=float)
        lat_values = np.asarray(dataset[lat_name].values, dtype=float)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to extract concentration grid: %s", exc, exc_info=True)
        return RasterResult(
            available=False,
            image_bytes=None,
            content_type="",
            acquired_at=None,
            reason=f"Failed to extract concentration grid: {exc}",
            debug=_exception_debug(exc),
        )

    try:
        image_bytes = _rasterize(values, lat_values)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to rasterize concentration grid: %s", exc, exc_info=True)
        return RasterResult(
            available=False,
            image_bytes=None,
            content_type="",
            acquired_at=None,
            reason=f"Failed to rasterize concentration grid: {exc}",
            debug=_exception_debug(exc),
        )

    return RasterResult(available=True, image_bytes=image_bytes, content_type="image/png", acquired_at=acquired_at, reason="OK")


def _rasterize(values: np.ndarray, lat_values: np.ndarray) -> bytes:
    """PNG-encode a (lat, lon) concentration grid (0-100%, NaN = no data /
    land / open water masked by the product) as a blue(ocean)-white(ice)
    raster with transparent no-data cells.

    Image row 0 must be the north edge. Rather than assume an ascending or
    descending latitude convention (the source of a real bug once already
    in this codebase's ensemble heatmap layer), the flip direction here is
    decided from `lat_values` itself.
    """
    from PIL import Image

    arr = np.clip(values, 0.0, 100.0)
    if lat_values[0] < lat_values[-1]:
        # lat ascends south-to-north, but array row 0 is the first (southern)
        # latitude -- flip so image row 0 becomes the northern edge.
        arr = np.flipud(arr)
        valid_mask = ~np.isnan(np.flipud(values))
    else:
        valid_mask = ~np.isnan(values)

    normalized = np.nan_to_num(arr, nan=0.0) / 100.0
    height, width = normalized.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    # Ocean (0%) -> dark blue, ice (100%) -> white -- consistent with this
    # app's existing ice-concentration palette elsewhere.
    rgba[..., 0] = (30 + normalized * 225).astype(np.uint8)
    rgba[..., 1] = (60 + normalized * 195).astype(np.uint8)
    rgba[..., 2] = (120 + normalized * 135).astype(np.uint8)
    rgba[..., 3] = np.where(valid_mask, 235, 0).astype(np.uint8)

    image = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
