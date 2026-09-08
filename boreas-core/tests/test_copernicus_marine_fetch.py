import io

import numpy as np
import pytest
import xarray as xr
from PIL import Image

from boreas_core.satellite import copernicus_marine_fetch


def _make_synthetic_dataset(*, lat_ascending: bool) -> xr.Dataset:
    lat = np.array([-72.0, -70.0, -68.0, -66.0, -64.0, -62.0, -60.0])
    if not lat_ascending:
        lat = lat[::-1]
    lon = np.array([60.0, 65.0, 70.0, 75.0, 80.0, 85.0, 90.0, 95.0])
    time = np.array(["2026-09-06"], dtype="datetime64[ns]")

    data = np.full((1, len(lat), len(lon)), 40.0)
    # A known no-data (NaN) cell at the first lat row, first lon column.
    data[0, 0, 0] = np.nan
    # A known high-concentration cell at the last lat row, last lon column.
    data[0, -1, -1] = 100.0

    return xr.Dataset(
        {"ice_conc": (("time", "lat", "lon"), data)},
        coords={"time": time, "lat": lat, "lon": lon},
    )


def test_fetch_returns_available_and_correctly_oriented_image(monkeypatch):
    ds = _make_synthetic_dataset(lat_ascending=True)  # -72 (south) ... -60 (north)
    monkeypatch.setattr("copernicusmarine.open_dataset", lambda **kwargs: ds)

    result = copernicus_marine_fetch.fetch_sea_ice_concentration_raster()

    assert result.available is True
    assert result.reason == "OK"
    assert result.acquired_at is not None

    image = Image.open(io.BytesIO(result.image_bytes))
    assert image.size == (8, 7)  # (lon, lat) == (width, height)

    pixels = np.array(image)
    # lat ascends south-to-north (row 0 of the array = -72, southernmost),
    # so after the north-on-top flip, image row 0 (north) should be the
    # *last* lat row's data -- the known high-concentration cell (100%,
    # last lon column) belongs at image row 0, last column.
    assert pixels[0, -1, 3] > 0  # opaque (valid data)
    assert pixels[0, -1, 0] > 200  # near-white (high concentration)

    # The known NaN cell (first lat row = southernmost = -72, first lon
    # column) should land at image row -1 (bottom = south), first column,
    # and be fully transparent.
    assert pixels[-1, 0, 3] == 0


def test_fetch_handles_already_descending_latitude(monkeypatch):
    ds = _make_synthetic_dataset(lat_ascending=False)  # -60 (north) ... -72 (south) already
    monkeypatch.setattr("copernicusmarine.open_dataset", lambda **kwargs: ds)

    result = copernicus_marine_fetch.fetch_sea_ice_concentration_raster()
    assert result.available is True

    image = Image.open(io.BytesIO(result.image_bytes))
    pixels = np.array(image)
    # No flip needed here -- array row 0 is already north (-60), so the
    # known NaN cell (row 0, col 0) stays at image row 0, col 0.
    assert pixels[0, 0, 3] == 0


def test_open_dataset_failure_degrades_gracefully(monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("401 Unauthorized")

    monkeypatch.setattr("copernicusmarine.open_dataset", _boom)

    result = copernicus_marine_fetch.fetch_sea_ice_concentration_raster()
    assert result.available is False
    assert "401" in result.reason or "Unauthorized" in result.reason


def test_missing_concentration_variable_degrades_gracefully(monkeypatch):
    ds = xr.Dataset(
        {"something_else": (("lat", "lon"), np.zeros((2, 2)))},
        coords={"lat": [-70.0, -60.0], "lon": [60.0, 70.0]},
    )
    monkeypatch.setattr("copernicusmarine.open_dataset", lambda **kwargs: ds)

    result = copernicus_marine_fetch.fetch_sea_ice_concentration_raster()
    assert result.available is False
    assert "concentration" in result.reason.lower() or "vars" in result.reason.lower()


def test_find_name_prefers_exact_match():
    assert copernicus_marine_fetch._find_name({"lat": None, "latitude_bounds": None}, ("lat", "latitude")) == "lat"


@pytest.mark.parametrize("missing", ["copernicusmarine"])
def test_import_error_degrades_gracefully(monkeypatch, missing):
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == missing:
            raise ImportError(f"No module named {missing}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    result = copernicus_marine_fetch.fetch_sea_ice_concentration_raster()
    assert result.available is False
