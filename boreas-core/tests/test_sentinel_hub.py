import pytest

from boreas_core.satellite import cdse_auth, sentinel_hub


@pytest.fixture(autouse=True)
def _clear_token_cache():
    cdse_auth._reset_cache_for_tests()
    yield
    cdse_auth._reset_cache_for_tests()


class _FakeResponse:
    def __init__(self, status_code, content=b"", text=""):
        self.status_code = status_code
        self.content = content
        self.text = text


def test_missing_credentials_returns_unavailable_without_network(monkeypatch):
    monkeypatch.delenv(cdse_auth.CDSE_CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(cdse_auth.CDSE_CLIENT_SECRET_ENV, raising=False)

    def _boom(*a, **k):
        raise AssertionError("httpx.post should not be called with no credentials")

    monkeypatch.setattr(sentinel_hub.httpx, "post", _boom)

    result = sentinel_hub.fetch_sentinel_quicklook("sentinel-1")
    assert result.available is False
    assert "CDSE_CLIENT_ID" in result.reason


def test_successful_fetch_returns_image_bytes(monkeypatch):
    monkeypatch.setenv(cdse_auth.CDSE_CLIENT_ID_ENV, "id")
    monkeypatch.setenv(cdse_auth.CDSE_CLIENT_SECRET_ENV, "secret")

    monkeypatch.setattr(
        sentinel_hub.stac,
        "discover_best_sentinel2_scene",
        lambda *a, **k: sentinel_hub.stac.Sentinel2Scene(
            item_id="S2_TEST_ITEM",
            datetime="2026-09-10T03:36:00Z",
            cloud_cover=12.0,
            bbox=[74.0, -70.5, 78.5, -68.3],
            geometry={},
            tile_id="T43DED",
        ),
    )

    captured_payload = {}

    def _post(url, json=None, headers=None, **kwargs):
        nonlocal captured_payload
        if "identity.dataspace" in url:
            return _FakeResponse(200, content=b"")
        captured_payload = json
        return _FakeResponse(200, content=b"\x89PNGfakebytes")

    def _fake_token(*a, **k):
        return "tok123"

    monkeypatch.setattr(sentinel_hub, "get_cdse_token", _fake_token)
    monkeypatch.setattr(sentinel_hub.httpx, "post", _post)

    result = sentinel_hub.fetch_sentinel_quicklook("sentinel-2")
    assert result.available is True
    assert result.image_bytes == b"\x89PNGfakebytes"
    assert result.content_type == "image/png"
    assert result.metadata is not None
    assert result.metadata["scene_id"] == "S2_TEST_ITEM"
    assert result.metadata["cloud_cover"] == 12.0

    # Verify timeRange is narrowed around the scene datetime
    time_filter = captured_payload["input"]["data"][0]["dataFilter"]["timeRange"]
    assert "2026-09-09" in time_filter["from"] or "2026-09-10" in time_filter["from"]
    assert "2026-09-10" in time_filter["to"]

    # Verify true-color RGBA evalscript with dataMask
    evalscript = captured_payload["evalscript"]
    assert "dataMask" in evalscript
    assert "sample.B04" in evalscript
    assert "bands: 4" in evalscript
    assert result.metadata["bbox"] == [74.0, -70.5, 78.5, -68.3]
    assert captured_payload["input"]["bounds"]["bbox"] == [74.0, -70.5, 78.5, -68.3]


def test_non_200_response_is_unavailable(monkeypatch):
    monkeypatch.setattr(sentinel_hub, "get_cdse_token", lambda *a, **k: "tok123")
    monkeypatch.setattr(
        sentinel_hub.stac,
        "discover_latest_sentinel1_scene",
        lambda *a, **k: sentinel_hub.stac.Sentinel1Scene(
            item_id="S1_MOCK",
            datetime="2026-09-18T00:00:00Z",
            instrument_mode="EW",
            polarizations=["HH", "HV"],
            bbox=[74.0, -70.5, 78.5, -68.3],
            geometry={},
        ),
    )
    monkeypatch.setattr(sentinel_hub.httpx, "post", lambda *a, **k: _FakeResponse(400, text="no scene found"))

    result = sentinel_hub.fetch_sentinel_quicklook("sentinel-1")
    assert result.available is False
    assert "400" in result.reason


def test_sentinel1_successful_fetch_dynamic_bands(monkeypatch):
    monkeypatch.setattr(sentinel_hub, "get_cdse_token", lambda *a, **k: "tok123")
    monkeypatch.setattr(
        sentinel_hub.stac,
        "discover_latest_sentinel1_scene",
        lambda *a, **k: sentinel_hub.stac.Sentinel1Scene(
            item_id="S1_MOCK_EW",
            datetime="2026-09-18T00:00:00Z",
            instrument_mode="EW",
            polarizations=["HH", "HV"],
            bbox=[74.0, -70.5, 78.5, -68.3],
            geometry={},
        ),
    )
    captured_payload = {}

    def _mock_post(url, json=None, headers=None, timeout=None):
        nonlocal captured_payload
        captured_payload = json
        return _FakeResponse(200, content=b"\x89PNGs1bytes")

    monkeypatch.setattr(sentinel_hub.httpx, "post", _mock_post)

    result = sentinel_hub.fetch_sentinel_quicklook("sentinel-1")
    assert result.available is True
    assert result.image_bytes == b"\x89PNGs1bytes"
    assert result.content_type == "image/png"
    # Verify dynamic band and filter selection
    data_filter = captured_payload["input"]["data"][0]["dataFilter"]
    assert data_filter["acquisitionMode"] == "EW"
    assert data_filter["polarization"] == "DH"
    assert 'input: ["HH", "HV"]' in captured_payload["evalscript"]


def test_unknown_source_id():
    result = sentinel_hub.fetch_sentinel_quicklook("sentinel-99")  # type: ignore[arg-type]
    assert result.available is False
