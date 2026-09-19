import pytest
from boreas_core.satellite import stac


def test_resolve_polarization_hh_hv():
    scene = stac.Sentinel1Scene(
        item_id="S1D_EW_GRDM_1SDH_20260918T144723_20260918T144827_004633_008A49_AD32_COG",
        datetime="2026-09-18T14:47:23Z",
        instrument_mode="EW",
        polarizations=["HH", "HV"],
        bbox=[74.0, -70.5, 78.5, -68.3],
        geometry={"type": "Polygon", "coordinates": []},
    )
    config = stac.resolve_polarization_config(scene)
    assert config.polarization_mode == "DH"
    assert config.acquisition_mode == "EW"
    assert config.bands == ["HH", "HV"]
    assert 'input: ["HH", "HV"]' in config.evalscript
    assert "sample.HH" in config.evalscript
    assert "sample.HV" in config.evalscript


def test_resolve_polarization_vv_vh():
    scene = stac.Sentinel1Scene(
        item_id="S1A_IW_GRDH_1SDV_20260918T120000_20260918T120030_000000_000000_0000_COG",
        datetime="2026-09-18T12:00:00Z",
        instrument_mode="IW",
        polarizations=["VV", "VH"],
        bbox=[-10.0, 50.0, -5.0, 55.0],
        geometry={"type": "Polygon", "coordinates": []},
    )
    config = stac.resolve_polarization_config(scene)
    assert config.polarization_mode == "DV"
    assert config.acquisition_mode == "IW"
    assert config.bands == ["VV", "VH"]
    assert 'input: ["VV", "VH"]' in config.evalscript
    assert "sample.VV" in config.evalscript
    assert "sample.VH" in config.evalscript


def test_resolve_polarization_single_pol():
    scene_hh = stac.Sentinel1Scene(
        item_id="S1D_IW_GRDH_1SSH_20260917T154409_COG",
        datetime="2026-09-17T15:44:09Z",
        instrument_mode="IW",
        polarizations=["HH"],
        bbox=[74.0, -70.5, 78.5, -68.3],
        geometry={},
    )
    config_hh = stac.resolve_polarization_config(scene_hh)
    assert config_hh.polarization_mode == "SH"
    assert config_hh.bands == ["HH"]
    assert 'input: ["HH"]' in config_hh.evalscript

    scene_vv = stac.Sentinel1Scene(
        item_id="S1A_IW_GRDH_1SSV_20260917T154409_COG",
        datetime="2026-09-17T15:44:09Z",
        instrument_mode="IW",
        polarizations=["VV"],
        bbox=[74.0, -70.5, 78.5, -68.3],
        geometry={},
    )
    config_vv = stac.resolve_polarization_config(scene_vv)
    assert config_vv.polarization_mode == "SV"
    assert config_vv.bands == ["VV"]
    assert 'input: ["VV"]' in config_vv.evalscript


def test_resolve_polarization_unsupported_or_missing():
    # Empty polarizations
    scene_empty = stac.Sentinel1Scene(
        item_id="S1_UNKNOWN",
        datetime="2026-09-18T00:00:00Z",
        instrument_mode="EW",
        polarizations=[],
        bbox=[],
        geometry={},
    )
    with pytest.raises(ValueError, match="Unsupported or missing Sentinel-1 polarization metadata"):
        stac.resolve_polarization_config(scene_empty)

    # Invalid/unsupported band
    scene_invalid = stac.Sentinel1Scene(
        item_id="S1_UNKNOWN",
        datetime="2026-09-18T00:00:00Z",
        instrument_mode="EW",
        polarizations=["XX", "YY"],
        bbox=[],
        geometry={},
    )
    with pytest.raises(ValueError, match="Unsupported or missing Sentinel-1 polarization metadata"):
        stac.resolve_polarization_config(scene_invalid)


class _MockResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json_data = json_data
        self.text = ""

    def json(self):
        return self._json_data


class _MockClient:
    def __init__(self, response):
        self.response = response
        self.posted_url = None
        self.posted_json = None

    def post(self, url, json=None, timeout=None):
        self.posted_url = url
        self.posted_json = json
        return self.response


def test_discover_latest_sentinel1_scene_parsing():
    mock_data = {
        "features": [
            {
                "id": "S1D_EW_GRDM_1SDH_TEST_COG",
                "bbox": [74.0, -70.5, 78.5, -68.3],
                "geometry": {"type": "Polygon", "coordinates": []},
                "properties": {
                    "datetime": "2026-09-18T14:47:23.113584Z",
                    "sar:instrument_mode": "EW",
                    "sar:polarizations": ["HH", "HV"],
                },
            }
        ]
    }
    client = _MockClient(_MockResponse(200, mock_data))
    scene = stac.discover_latest_sentinel1_scene(
        bbox=(74.0, -70.5, 78.5, -68.3),
        lookback_days=14,
        client=client,
    )
    assert scene is not None
    assert scene.item_id == "S1D_EW_GRDM_1SDH_TEST_COG"
    assert scene.datetime == "2026-09-18T14:47:23.113584Z"
    assert scene.instrument_mode == "EW"
    assert scene.polarizations == ["HH", "HV"]
    assert client.posted_json["collections"] == ["sentinel-1-grd"]
    assert client.posted_json["bbox"] == [74.0, -70.5, 78.5, -68.3]


def test_discover_latest_sentinel1_scene_empty():
    client = _MockClient(_MockResponse(200, {"features": []}))
    scene = stac.discover_latest_sentinel1_scene(
        bbox=(74.0, -70.5, 78.5, -68.3),
        lookback_days=14,
        client=client,
    )
    assert scene is None


def test_discover_latest_sentinel1_scene_http_error():
    client = _MockClient(_MockResponse(500, {}))
    scene = stac.discover_latest_sentinel1_scene(
        bbox=(74.0, -70.5, 78.5, -68.3),
        lookback_days=14,
        client=client,
    )
    assert scene is None
