import pytest
from unittest.mock import AsyncMock, patch
from pathlib import Path
from transcoder import Transcoder
from config import Config

@pytest.fixture
def transcoder(tmp_path: Path):
    config = Config(tmp_path)
    return Transcoder(config)

@pytest.mark.asyncio
async def test_transcoder_start_stop(transcoder: Transcoder, tmp_path: Path):
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.stderr.readline = AsyncMock(side_effect=[b"ffmpeg version 4.2", b""])
        mock_proc.wait = AsyncMock(return_value=0)
        mock_exec.return_value = mock_proc

        await transcoder.start("http://test.url/stream.m3u8", tmp_path / "output.m3u8")
        assert transcoder.is_active is True
        assert transcoder.process is not None

        await transcoder.stop()
        assert transcoder.is_active is False
        assert transcoder.process is None
