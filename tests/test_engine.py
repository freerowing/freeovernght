import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from pathlib import Path
from config import Config
from engine import RestreamEngine, EngineState

@pytest.fixture
def config(tmp_path: Path):
    cfg = Config(tmp_path)
    cfg.email = "test@test.com"
    cfg.password = "password"
    cfg.event_url = "http://test.com"
    return cfg

@pytest.mark.asyncio
async def test_engine_initial_state(config):
    engine = RestreamEngine(config)
    assert engine.state == EngineState.IDLE
    assert not engine.is_running
    assert engine.active_url is None

@pytest.mark.asyncio
async def test_engine_missing_config(config):
    config.event_url = ""  # Invalidates config
    engine = RestreamEngine(config)

    await engine.start()
    await asyncio.sleep(0.1)  # Let event loop run

    assert engine.state == EngineState.ERROR
    assert "Credentials or Event URL not configured" in engine.error_message
    await engine.stop()

@pytest.mark.asyncio
@patch("engine.sniff_stream_url")
async def test_engine_sniff_and_transcode_short_run(mock_sniff, config):
    mock_sniff.return_value = "http://fake.m3u8"
    engine = RestreamEngine(config)

    # Mock transcoder to exit immediately (duration < 60s)
    engine.transcoder.start = AsyncMock()
    engine.transcoder.wait = AsyncMock(return_value=0)
    engine.transcoder.stop = AsyncMock()

    await engine.start()
    await asyncio.sleep(0.1)  # Let event loop process sniffing and transcoder start

    # Should end up in ERROR because of quick exit
    assert engine.state == EngineState.ERROR
    assert engine.active_url is None

    await engine.stop()
