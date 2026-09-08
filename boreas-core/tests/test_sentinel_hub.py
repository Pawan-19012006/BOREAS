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

    def _post(url, **kwargs):
        if "identity.dataspace" in url:
            return _FakeResponse(200, content=b"")
        return _FakeResponse(200, content=b"\x89PNGfakebytes")

    def _fake_token(*a, **k):
        return "tok123"

    monkeypatch.setattr(sentinel_hub, "get_cdse_token", _fake_token)
    monkeypatch.setattr(sentinel_hub.httpx, "post", lambda *a, **k: _FakeResponse(200, content=b"\x89PNGfakebytes"))

    result = sentinel_hub.fetch_sentinel_quicklook("sentinel-2")
    assert result.available is True
    assert result.image_bytes == b"\x89PNGfakebytes"
    assert result.content_type == "image/png"


def test_non_200_response_is_unavailable(monkeypatch):
    monkeypatch.setattr(sentinel_hub, "get_cdse_token", lambda *a, **k: "tok123")
    monkeypatch.setattr(sentinel_hub.httpx, "post", lambda *a, **k: _FakeResponse(400, text="no scene found"))

    result = sentinel_hub.fetch_sentinel_quicklook("sentinel-1")
    assert result.available is False
    assert "400" in result.reason


def test_unknown_source_id():
    result = sentinel_hub.fetch_sentinel_quicklook("sentinel-99")  # type: ignore[arg-type]
    assert result.available is False
