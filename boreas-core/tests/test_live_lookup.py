import pytest

from boreas_core.vessels import live_lookup
from boreas_core.vessels.roster import get_vessel_by_id

VESSEL = get_vessel_by_id("vasiliy_golovnin")


@pytest.fixture(autouse=True)
def _clear_cache():
    live_lookup._CACHE.clear()
    yield
    live_lookup._CACHE.clear()


class _FakeResponse:
    def __init__(self, status_code, json_body=None, headers=None):
        self.status_code = status_code
        self._json_body = json_body or {}
        self.headers = headers or {}

    def json(self):
        return self._json_body


def test_no_api_key_returns_not_connected_without_network_call(monkeypatch):
    monkeypatch.delenv(live_lookup.VESSELAPI_KEY_ENV, raising=False)

    def _boom(*args, **kwargs):
        raise AssertionError("httpx.get should not be called when no API key is configured")

    monkeypatch.setattr(live_lookup.httpx, "get", _boom)

    result = live_lookup.lookup_vessel_position(VESSEL)
    assert result.status == live_lookup.STATUS_NOT_CONNECTED
    assert result.lon, result.lat == VESSEL.home_port_lonlat
    assert result.timestamp is None


def test_successful_lookup_returns_live(monkeypatch):
    monkeypatch.setenv(live_lookup.VESSELAPI_KEY_ENV, "test-key")
    monkeypatch.setattr(
        live_lookup.httpx,
        "get",
        lambda *a, **k: _FakeResponse(
            200, {"latitude": -34.1, "longitude": 18.5, "timestamp": "2026-01-01T00:00:00Z"}
        ),
    )

    result = live_lookup.lookup_vessel_position(VESSEL)
    assert result.status == live_lookup.STATUS_LIVE
    assert result.lat == pytest.approx(-34.1)
    assert result.lon == pytest.approx(18.5)
    assert result.timestamp == "2026-01-01T00:00:00Z"


def test_404_returns_beyond_ais_range_with_home_port_fallback(monkeypatch):
    monkeypatch.setenv(live_lookup.VESSELAPI_KEY_ENV, "test-key")
    monkeypatch.setattr(live_lookup.httpx, "get", lambda *a, **k: _FakeResponse(404))

    result = live_lookup.lookup_vessel_position(VESSEL)
    assert result.status == live_lookup.STATUS_BEYOND_RANGE
    assert (result.lon, result.lat) == VESSEL.home_port_lonlat
    assert result.timestamp is None


def test_network_error_returns_not_connected(monkeypatch):
    monkeypatch.setenv(live_lookup.VESSELAPI_KEY_ENV, "test-key")

    def _raise(*a, **k):
        raise live_lookup.httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(live_lookup.httpx, "get", _raise)

    result = live_lookup.lookup_vessel_position(VESSEL)
    assert result.status == live_lookup.STATUS_NOT_CONNECTED


def test_result_is_cached_within_ttl(monkeypatch):
    monkeypatch.setenv(live_lookup.VESSELAPI_KEY_ENV, "test-key")
    call_count = 0

    def _get(*a, **k):
        nonlocal call_count
        call_count += 1
        return _FakeResponse(200, {"latitude": -34.1, "longitude": 18.5})

    monkeypatch.setattr(live_lookup.httpx, "get", _get)

    first = live_lookup.lookup_vessel_position(VESSEL)
    second = live_lookup.lookup_vessel_position(VESSEL)
    assert call_count == 1
    assert first == second


def test_vessel_without_imo_is_not_connected(monkeypatch):
    monkeypatch.setenv(live_lookup.VESSELAPI_KEY_ENV, "test-key")
    from dataclasses import replace

    vessel_no_imo = replace(VESSEL, imo=None)

    def _boom(*args, **kwargs):
        raise AssertionError("httpx.get should not be called when no IMO is on file")

    monkeypatch.setattr(live_lookup.httpx, "get", _boom)

    result = live_lookup.lookup_vessel_position(vessel_no_imo)
    assert result.status == live_lookup.STATUS_NOT_CONNECTED
