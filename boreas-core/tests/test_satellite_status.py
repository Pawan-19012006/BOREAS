"""Satellite status must never claim CONNECTED without a real provider
request having succeeded.

Every test here mocks the provider: these assert the honesty rules, not
CDSE's availability, and must not depend on the network.
"""

import pytest
from fastapi.testclient import TestClient

from boreas_core.api.server import app
from boreas_core.satellite import status as status_mod
from boreas_core.satellite.cdse_auth import CdseAuthError
from boreas_core.satellite.stac import Sentinel1Scene, Sentinel2Scene

client = TestClient(app)

CDSE_VARS = ("CDSE_CLIENT_ID", "CDSE_CLIENT_SECRET")
MARINE_VARS = ("COPERNICUSMARINE_SERVICE_USERNAME", "COPERNICUSMARINE_SERVICE_PASSWORD")


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    status_mod._clear_cache_for_tests()
    yield
    status_mod._clear_cache_for_tests()


def _with_credentials(monkeypatch):
    monkeypatch.setenv("CDSE_CLIENT_ID", "id")
    monkeypatch.setenv("CDSE_CLIENT_SECRET", "secret")


def _without_credentials(monkeypatch):
    for var in CDSE_VARS + MARINE_VARS:
        monkeypatch.delenv(var, raising=False)


def _mock_token(monkeypatch, *, ok=True):
    if ok:
        monkeypatch.setattr(status_mod, "get_cdse_token", lambda **kw: "token")
    else:
        def _raise(**kw):
            raise CdseAuthError("invalid_client")

        monkeypatch.setattr(status_mod, "get_cdse_token", _raise)


S1_SCENE = Sentinel1Scene(
    item_id="S1A_EW_GRDM_TEST",
    datetime="2026-09-23T14:55:34Z",
    instrument_mode="EW",
    polarizations=["HH", "HV"],
    bbox=[69.6, -69.4, 82.9, -64.0],
    geometry={},
)
S2_SCENE = Sentinel2Scene(
    item_id="S2B_MSIL2A_TEST",
    datetime="2026-09-20T03:36:19Z",
    cloud_cover=12.5,
    bbox=[75.0, -70.4, 77.9, -69.4],
    geometry={},
    tile_id="MGRS-43DEC",
)


def _mock_stac(monkeypatch, *, s1=S1_SCENE, s2=S2_SCENE):
    monkeypatch.setattr(status_mod.stac, "discover_latest_sentinel1_scene", lambda *a, **k: s1)
    monkeypatch.setattr(status_mod.stac, "discover_best_sentinel2_scene", lambda *a, **k: s2)


# ------------------------------------------------------------------- states ---


def test_missing_credentials_report_demo_not_connected(monkeypatch):
    """The honesty rule: no credentials means simulated data, said plainly."""
    _without_credentials(monkeypatch)
    statuses = status_mod.get_all_statuses()

    assert set(statuses) == {"sentinel-1", "sentinel-2", "copernicus-marine"}
    for s in statuses.values():
        assert s.state == status_mod.STATE_DEMO
        assert s.connected is False
        assert s.observation is None
        assert s.reason


def test_configured_credentials_alone_never_report_connected(monkeypatch):
    """Regression guard for the original bug: presence of env vars is not
    evidence of connectivity. If the provider request fails, the state is an
    error -- never CONNECTED."""
    _with_credentials(monkeypatch)
    _mock_token(monkeypatch, ok=False)

    s = status_mod.get_source_status("sentinel-1")
    assert s.state == status_mod.STATE_CONNECTION_ERROR
    assert s.connected is False
    assert s.credentials_configured is True
    assert s.observation is None
    assert "authentication failed" in s.reason.lower()


def test_successful_probe_reports_connected_with_real_provenance(monkeypatch):
    _with_credentials(monkeypatch)
    _mock_token(monkeypatch)
    _mock_stac(monkeypatch)

    s1 = status_mod.get_source_status("sentinel-1")
    assert s1.state == status_mod.STATE_CONNECTED
    assert s1.connected is True
    assert s1.imagery_available is True
    assert s1.checked_at
    assert s1.observation is not None
    assert s1.observation.product_id == "S1A_EW_GRDM_TEST"
    assert s1.observation.acquired_at == "2026-09-23T14:55:34Z"
    assert s1.observation.collection == "sentinel-1-grd"
    assert s1.observation.extra["polarizations"] == ["HH", "HV"]

    s2 = status_mod.get_source_status("sentinel-2")
    assert s2.observation.product_id == "S2B_MSIL2A_TEST"
    assert s2.observation.extra["cloud_cover"] == 12.5


def test_stac_failure_is_a_connection_error(monkeypatch):
    _with_credentials(monkeypatch)
    _mock_token(monkeypatch)

    def _boom(*a, **k):
        raise RuntimeError("read timeout")

    monkeypatch.setattr(status_mod.stac, "discover_latest_sentinel1_scene", _boom)

    s = status_mod.get_source_status("sentinel-1")
    assert s.state == status_mod.STATE_CONNECTION_ERROR
    assert s.connected is False
    assert "read timeout" in s.reason


def test_no_scene_over_aoi_is_connected_but_not_an_observation(monkeypatch):
    """The provider answered, so the connection is real -- but an empty result
    must not be dressed up as an observation."""
    _with_credentials(monkeypatch)
    _mock_token(monkeypatch)
    _mock_stac(monkeypatch, s1=None, s2=None)

    s = status_mod.get_source_status("sentinel-1")
    assert s.state == status_mod.STATE_CONNECTED
    assert s.observation is None
    assert s.imagery_available is False


def test_copernicus_marine_never_claims_connected(monkeypatch):
    """It has no lightweight probe, so it can never prove it is live."""
    for configured in (True, False):
        status_mod._clear_cache_for_tests()
        if configured:
            monkeypatch.setenv("COPERNICUSMARINE_SERVICE_USERNAME", "u")
            monkeypatch.setenv("COPERNICUSMARINE_SERVICE_PASSWORD", "p")
        else:
            for var in MARINE_VARS:
                monkeypatch.delenv(var, raising=False)

        s = status_mod.get_source_status("copernicus-marine")
        assert s.connected is False
        assert s.state == status_mod.STATE_DEMO
        assert s.credentials_configured is configured


@pytest.mark.parametrize("has_id,has_secret", [(True, False), (False, True), (False, False)])
def test_cdse_requires_both_credentials(monkeypatch, has_id, has_secret):
    _without_credentials(monkeypatch)
    if has_id:
        monkeypatch.setenv("CDSE_CLIENT_ID", "id")
    if has_secret:
        monkeypatch.setenv("CDSE_CLIENT_SECRET", "secret")

    assert status_mod.get_source_status("sentinel-1").state == status_mod.STATE_DEMO
    assert status_mod.get_source_status("sentinel-2").connected is False


def test_probe_result_is_cached_then_refreshable(monkeypatch):
    _with_credentials(monkeypatch)
    _mock_token(monkeypatch)
    calls = {"n": 0}

    def _counting(*a, **k):
        calls["n"] += 1
        return S1_SCENE

    monkeypatch.setattr(status_mod.stac, "discover_latest_sentinel1_scene", _counting)

    status_mod.get_source_status("sentinel-1")
    status_mod.get_source_status("sentinel-1")
    assert calls["n"] == 1, "probe should be cached, not re-run per request"

    status_mod.get_source_status("sentinel-1", force=True)
    assert calls["n"] == 2


# --------------------------------------------------------------- API surface ---


def test_satellite_status_endpoint_exposes_state_and_provenance(monkeypatch):
    _with_credentials(monkeypatch)
    _mock_token(monkeypatch)
    _mock_stac(monkeypatch)

    body = client.get("/satellite/status").json()
    assert set(body["sources"]) == {"sentinel-1", "sentinel-2", "copernicus-marine"}

    s1 = body["sources"]["sentinel-1"]
    assert s1["state"] == "CONNECTED"
    assert s1["connected"] is True
    assert s1["provider"] == "Copernicus Data Space Ecosystem"
    assert s1["observation"]["product_id"] == "S1A_EW_GRDM_TEST"
    assert s1["checked_at"]

    marine = body["sources"]["copernicus-marine"]
    assert marine["state"] == "DEMO"
    assert marine["observation"] is None


def test_satellite_status_endpoint_reports_demo_without_credentials(monkeypatch):
    _without_credentials(monkeypatch)
    body = client.get("/satellite/status").json()
    for source in body["sources"].values():
        assert source["state"] == "DEMO"
        assert source["connected"] is False
        assert source["observation"] is None


# ------------------------------------------------------------------ quicklook ---


def test_quicklook_endpoint_returns_503_when_not_connected(monkeypatch):
    _without_credentials(monkeypatch)
    from boreas_core.satellite import quicklook

    quicklook._clear_cache_for_tests()
    response = client.get("/satellite/sentinel-1/quicklook")
    assert response.status_code == 503
    assert "detail" in response.json()


def test_quicklook_endpoint_returns_image_on_success(monkeypatch):
    from boreas_core.satellite import quicklook

    quicklook._clear_cache_for_tests()
    monkeypatch.setattr(
        quicklook,
        "_fetch",
        lambda source_id: quicklook.Quicklook(
            available=True, image_bytes=b"\x89PNGfake", content_type="image/png", reason="OK"
        ),
    )

    response = client.get("/satellite/sentinel-2/quicklook")
    assert response.status_code == 200
    assert response.content == b"\x89PNGfake"
    assert response.headers["content-type"] == "image/png"
    quicklook._clear_cache_for_tests()


def test_quicklook_endpoint_unknown_source():
    from boreas_core.satellite import quicklook

    quicklook._clear_cache_for_tests()
    assert client.get("/satellite/not-a-real-source/quicklook").status_code == 503
