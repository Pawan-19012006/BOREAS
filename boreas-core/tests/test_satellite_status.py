import pytest
from fastapi.testclient import TestClient

from boreas_core.api.server import app
from boreas_core.satellite.status import get_all_statuses

client = TestClient(app)


def test_get_all_statuses_reports_disconnected_without_env_vars(monkeypatch):
    for var in (
        "CDSE_CLIENT_ID",
        "CDSE_CLIENT_SECRET",
        "COPERNICUSMARINE_SERVICE_USERNAME",
        "COPERNICUSMARINE_SERVICE_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)

    statuses = get_all_statuses()
    assert set(statuses) == {"sentinel-1", "sentinel-2", "copernicus-marine"}
    assert all(not s.connected for s in statuses.values())
    assert all(s.reason for s in statuses.values())


def test_get_all_statuses_reports_connected_with_env_vars(monkeypatch):
    monkeypatch.setenv("CDSE_CLIENT_ID", "id")
    monkeypatch.setenv("CDSE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("COPERNICUSMARINE_SERVICE_USERNAME", "user")
    monkeypatch.setenv("COPERNICUSMARINE_SERVICE_PASSWORD", "pass")

    statuses = get_all_statuses()
    assert all(s.connected for s in statuses.values())


def test_satellite_status_endpoint():
    response = client.get("/satellite/status")
    assert response.status_code == 200
    body = response.json()
    assert set(body["sources"]) == {"sentinel-1", "sentinel-2", "copernicus-marine"}
    for source in body["sources"].values():
        assert "connected" in source
        assert "reason" in source


def test_quicklook_endpoint_returns_503_when_not_connected(monkeypatch):
    for var in (
        "CDSE_CLIENT_ID",
        "CDSE_CLIENT_SECRET",
        "COPERNICUSMARINE_SERVICE_USERNAME",
        "COPERNICUSMARINE_SERVICE_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)
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
        lambda source_id: quicklook.Quicklook(available=True, image_bytes=b"\x89PNGfake", content_type="image/png", reason="OK"),
    )

    response = client.get("/satellite/sentinel-2/quicklook")
    assert response.status_code == 200
    assert response.content == b"\x89PNGfake"
    assert response.headers["content-type"] == "image/png"
    quicklook._clear_cache_for_tests()


def test_quicklook_endpoint_unknown_source():
    from boreas_core.satellite import quicklook

    quicklook._clear_cache_for_tests()
    response = client.get("/satellite/not-a-real-source/quicklook")
    assert response.status_code == 503


@pytest.mark.parametrize("has_id,has_secret", [(True, False), (False, True), (False, False)])
def test_cdse_requires_both_credentials(monkeypatch, has_id, has_secret):
    monkeypatch.delenv("CDSE_CLIENT_ID", raising=False)
    monkeypatch.delenv("CDSE_CLIENT_SECRET", raising=False)
    if has_id:
        monkeypatch.setenv("CDSE_CLIENT_ID", "id")
    if has_secret:
        monkeypatch.setenv("CDSE_CLIENT_SECRET", "secret")

    statuses = get_all_statuses()
    assert statuses["sentinel-1"].connected is False
    assert statuses["sentinel-2"].connected is False
