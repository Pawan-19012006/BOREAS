import pytest

from boreas_core.satellite import quicklook, sentinel_hub
from boreas_core.satellite.sentinel_hub import QuicklookResult


@pytest.fixture(autouse=True)
def _clear_cache():
    quicklook._clear_cache_for_tests()
    yield
    quicklook._clear_cache_for_tests()


def test_successful_fetch_is_cached(monkeypatch):
    call_count = 0

    def _fake_fetch(source_id, **kwargs):
        nonlocal call_count
        call_count += 1
        return QuicklookResult(available=True, image_bytes=b"abc", content_type="image/png", reason="OK")

    monkeypatch.setattr(sentinel_hub, "fetch_sentinel_quicklook", _fake_fetch)

    first = quicklook.get_quicklook("sentinel-1")
    second = quicklook.get_quicklook("sentinel-1")
    assert call_count == 1
    assert first.available is True
    assert second.image_bytes == b"abc"


def test_failed_fetch_is_not_cached(monkeypatch):
    call_count = 0

    def _fake_fetch(source_id, **kwargs):
        nonlocal call_count
        call_count += 1
        return QuicklookResult(available=False, image_bytes=None, content_type="", reason="not connected")

    monkeypatch.setattr(sentinel_hub, "fetch_sentinel_quicklook", _fake_fetch)

    quicklook.get_quicklook("sentinel-2")
    quicklook.get_quicklook("sentinel-2")
    assert call_count == 2  # retried each time, not stuck on a stale failure


def test_unknown_source_id_is_unavailable():
    result = quicklook.get_quicklook("not-a-real-source")
    assert result.available is False
