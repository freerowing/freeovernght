import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sniffer import _parse_variant_line, _select_best_variant, resolve_highest_quality_stream

def test_parse_variant_line():
    line = '#EXT-X-STREAM-INF:BANDWIDTH=5000000,RESOLUTION=1920x1080'
    bw, res = _parse_variant_line(line)
    assert bw == 5000000
    assert res == '1920x1080'

    line2 = '#EXT-X-STREAM-INF:BANDWIDTH=1000'
    bw2, res2 = _parse_variant_line(line2)
    assert bw2 == 1000
    assert res2 == ''

def test_select_best_variant():
    variants = [
        (1000, "1280x720", "http://720p.m3u8"),
        (5000, "1920x1080", "http://1080p.m3u8"),
        (8000, "4k", "http://4k.m3u8")
    ]
    # It prefers 1080p
    assert _select_best_variant(variants) == "http://1080p.m3u8"

    variants2 = [
        (1000, "720p", "http://720p.m3u8"),
        (3000, "720p_high", "http://720p_high.m3u8"),
    ]
    # Fallback to highest bandwidth
    assert _select_best_variant(variants2) == "http://720p_high.m3u8"

@pytest.mark.asyncio
async def test_resolve_highest_quality_stream():
    # Test skipping non m3u8
    assert await resolve_highest_quality_stream("http://test.com/video.mp4") == "http://test.com/video.mp4"

    # Test valid m3u8
    mock_resp = MagicMock()
    mock_resp.text = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=1000,RESOLUTION=720p
720.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=5000,RESOLUTION=1080p
1080.m3u8"""

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        url = await resolve_highest_quality_stream("http://test.com/master.m3u8")
        assert url == "http://test.com/1080.m3u8"

        # Test missing stream info
        mock_resp.text = "no stream info here"
        url2 = await resolve_highest_quality_stream("http://test.com/master.m3u8")
        assert url2 == "http://test.com/master.m3u8"

from config import Config
from pathlib import Path
from sniffer import _attempt_direct_navigation

@pytest.mark.asyncio
async def test_attempt_direct_navigation(tmp_path: Path):
    config = Config(tmp_path)
    cookies_path = tmp_path / "cookies.json"

    page = AsyncMock()
    page.goto = AsyncMock()
    page.url = "http://test.com/event"

    locator_mock = MagicMock()
    locator_mock.is_visible = AsyncMock(return_value=False)
    page.locator = MagicMock(return_value=locator_mock)

    # Should return False because no cookies
    res = await _attempt_direct_navigation(page, config, cookies_path, [None])
    assert res is False

    cookies_path.write_text("{}")

    # Should return True because url captured
    captured = ["http://captured.m3u8"]
    res2 = await _attempt_direct_navigation(page, config, cookies_path, captured)
    assert res2 is True

from sniffer import _perform_full_login

@pytest.mark.asyncio
async def test_perform_full_login(tmp_path: Path):
    config = Config(tmp_path)
    cookies_path = tmp_path / "cookies.json"

    page = AsyncMock()
    context = AsyncMock()

    # Mock it so it proceeds with full login (not logged in already)
    page.url = "http://test.com/login"

    # Mock locator
    locator_mock = AsyncMock()
    page.locator = MagicMock(return_value=locator_mock)

    await _perform_full_login(page, context, config, cookies_path)

    page.goto.assert_called_with(config.login_url, timeout=30000, wait_until="domcontentloaded")
    assert page.locator.call_count >= 2
    context.storage_state.assert_called()
