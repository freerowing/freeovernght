import asyncio
import logging
import time
from enum import StrEnum
from typing import Optional, Any
from config import Config
from sniffer import sniff_stream_url
from transcoder import Transcoder

logger = logging.getLogger("restreamer")


class EngineState(StrEnum):
    IDLE = "IDLE"
    SNIFFING = "SNIFFING"
    TRANSCODING = "TRANSCODING"
    ERROR = "ERROR"


class RestreamEngine:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.transcoder = Transcoder(self.config)
        self.state = EngineState.IDLE
        self.active_url: Optional[str] = None
        self.error_message: Optional[str] = None
        self.start_time: Optional[float] = None
        self.is_running = False

        self._loop_task: Optional[asyncio.Task] = None

    def set_state(self, state: EngineState | str) -> None:
        state_enum = EngineState(state)
        logger.info(f"Engine transition: {self.state} ➔ {state_enum}")
        self.state = state_enum
        if state_enum == EngineState.TRANSCODING:
            self.start_time = time.time()
        elif state_enum in (EngineState.IDLE, EngineState.ERROR):
            self.start_time = None

    async def start(self) -> None:
        """Starts the engine state loop."""
        if self.is_running:
            return

        self.is_running = True
        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info("Restream Engine started.")

    async def stop(self) -> None:
        """Stops the engine loop and kills active processes."""
        if not self.is_running:
            return

        self.is_running = False

        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None

        await self.transcoder.stop()
        self.set_state(EngineState.IDLE)
        logger.info("Restream Engine stopped.")

    async def force_refresh(self) -> None:
        """Forcibly clears cached credentials/URL and restarts the sniffing cycle."""
        logger.info("Forcing engine stream refresh...")
        # Clear cache file
        cache_file = self.config.stream_url_cache
        if cache_file.exists():
            try:
                cache_file.unlink()
            except Exception as e:
                logger.warning(f"Could not delete stream url cache file: {e}")

        # Clear cookies file
        cookies_file = self.config.cookies_cache
        if cookies_file.exists():
            try:
                cookies_file.unlink()
                logger.info("Deleted cached session cookies.")
            except Exception as e:
                logger.warning(f"Could not delete cookies cache file: {e}")

        self.active_url = None
        await self.transcoder.stop()

        # If the loop is running, we cancel the current wait/sleep and let the loop continue
        if self.is_running and self._loop_task:
            # We don't want to stop the engine, just restart the loop cycle.
            # Stopping and starting achieves this safely.
            await self.stop()
            await self.start()

    async def _check_validation(self) -> bool:
        if not self.config.is_valid():
            self.error_message = "Credentials or Event URL not configured. Edit settings to continue."
            self.set_state(EngineState.ERROR)
            await asyncio.sleep(5)
            return False
        return True

    def _check_cache(self) -> None:
        cache_file = self.config.stream_url_cache
        if not self.active_url and cache_file.exists():
            try:
                mtime = cache_file.stat().st_mtime
                age_mins = (time.time() - mtime) / 60.0
                if age_mins > 5.0:
                    logger.info(f"Cached stream URL is stale (age: {age_mins:.1f}m). Deleting and re-sniffing.")
                    cache_file.unlink(missing_ok=True)
                else:
                    self.active_url = cache_file.read_text().strip()
                    logger.info(f"Loaded stream URL from local cache (age: {age_mins:.1f}m).")
            except Exception as e:
                logger.warning(f"Failed to read/validate cache file: {e}")

    async def _acquire_stream(self) -> bool:
        if not self.active_url:
            self.set_state(EngineState.SNIFFING)
            self.error_message = None
            try:
                self.active_url = await sniff_stream_url(self.config)
            except Exception as e:
                self.error_message = f"Browser automation error: {str(e)}"
                self.set_state(EngineState.ERROR)
                logger.error(f"Failed to acquire stream: {e}")
                return True
        return False

    async def _run_transcoder(self) -> bool:
        self.set_state(EngineState.TRANSCODING)
        self.error_message = None
        output_file = self.config.media_dir / "local.m3u8"
        transcode_start_time = time.time()

        try:
            assert self.active_url is not None
            await self.transcoder.start(self.active_url, output_file)
            await self.transcoder.wait()

            duration = time.time() - transcode_start_time
            if duration < 60.0:
                logger.warning(f"FFmpeg terminated quickly (in {duration:.1f}s). Stream offline or link expired.")
                self.active_url = None
                self.config.stream_url_cache.unlink(missing_ok=True)
                self.error_message = "Stream offline or failed to transcode."
                self.set_state(EngineState.ERROR)
                return True
            else:
                logger.info(f"FFmpeg process ended after successful run of {duration:.1f}s.")
                if self.is_running:
                    await asyncio.sleep(2)
                return False

        except Exception as e:
            logger.error(f"Error during transcoding process: {e}")
            self.active_url = None
            self.config.stream_url_cache.unlink(missing_ok=True)
            self.error_message = f"Transcoder failed: {str(e)}"
            self.set_state(EngineState.ERROR)
            return True

    async def _run_loop(self) -> None:
        """Main orchestrator loop."""
        retry_delay = 10.0

        while self.is_running:
            try:
                if not await self._check_validation():
                    continue

                self._check_cache()

                if await self._acquire_stream():
                    logger.info(f"Retrying sniffing in {retry_delay:.1f}s (exponential backoff)...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 300.0)
                    continue

                if await self._run_transcoder():
                    logger.info(f"Retrying sniffing in {retry_delay:.1f}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 300.0)
                else:
                    retry_delay = 10.0

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.critical(f"Critical error in engine loop: {e}", exc_info=True)
                self.error_message = f"System error: {str(e)}"
                self.set_state(EngineState.ERROR)
                await asyncio.sleep(10)

    def get_status(self) -> dict[str, Any]:
        uptime = 0
        if self.start_time:
            uptime = int(time.time() - self.start_time)

        return {
            "state": self.state,
            "is_running": self.is_running,
            "uptime": uptime
        }
