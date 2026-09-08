import pytest

from boreas_core.satellite import cdse_auth


@pytest.fixture(autouse=True)
def _clear_token_cache():
    cdse_auth._reset_cache_for_tests()
    yield
    cdse_auth._reset_cache_for_tests()


class _FakeResponse:
    def __init__(self, status_code, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body or {}
        self.text = text

    def json(self):
        return self._json_body


def test_missing_credentials_raises_without_network_call(monkeypatch):
    monkeypatch.delenv(cdse_auth.CDSE_CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(cdse_auth.CDSE_CLIENT_SECRET_ENV, raising=False)

    def _boom(*a, **k):
        raise AssertionError("httpx.post should not be called with no credentials")

    monkeypatch.setattr(cdse_auth.httpx, "post", _boom)

    with pytest.raises(cdse_auth.CdseAuthError):
        cdse_auth.get_cdse_token()


def test_successful_token_fetch(monkeypatch):
    monkeypatch.setenv(cdse_auth.CDSE_CLIENT_ID_ENV, "id")
    monkeypatch.setenv(cdse_auth.CDSE_CLIENT_SECRET_ENV, "secret")
    monkeypatch.setattr(
        cdse_auth.httpx, "post", lambda *a, **k: _FakeResponse(200, {"access_token": "tok123", "expires_in": 600})
    )

    token = cdse_auth.get_cdse_token()
    assert token == "tok123"


def test_token_is_cached(monkeypatch):
    monkeypatch.setenv(cdse_auth.CDSE_CLIENT_ID_ENV, "id")
    monkeypatch.setenv(cdse_auth.CDSE_CLIENT_SECRET_ENV, "secret")
    call_count = 0

    def _post(*a, **k):
        nonlocal call_count
        call_count += 1
        return _FakeResponse(200, {"access_token": "tok123", "expires_in": 600})

    monkeypatch.setattr(cdse_auth.httpx, "post", _post)

    cdse_auth.get_cdse_token()
    cdse_auth.get_cdse_token()
    assert call_count == 1


def test_http_error_raises_auth_error(monkeypatch):
    monkeypatch.setenv(cdse_auth.CDSE_CLIENT_ID_ENV, "id")
    monkeypatch.setenv(cdse_auth.CDSE_CLIENT_SECRET_ENV, "secret")
    monkeypatch.setattr(cdse_auth.httpx, "post", lambda *a, **k: _FakeResponse(401, text="invalid client"))

    with pytest.raises(cdse_auth.CdseAuthError):
        cdse_auth.get_cdse_token()
