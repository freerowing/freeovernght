import asyncio
import logging
import time
from typing import Optional
from config import Config
from sniffer import sniff_stream_url
from transcoder import Transcoder

logger = logging.getLogger("restreamer")


class RestreamEngine:
    def __init__(self, config: Config):
        self.config = config
        self.transcoder = Transcoder()
        self.state = "IDLE"  # IDLE, SNIFFING, TRANSCODING, ERROR
        self.active_url: Optional[str] = None
        self.error_message: Optional[str] = None
        self.start_time: Optional[float] = None
        self.is_running = False
        
        self._loop_task: Optional[asyncio.Task] = None
        self._shutdown_evt = asyncio.Event()

    def set_state(self, state: str):
        logger.info(f"Engine transition: {self.state} ➔ {state}")
        self.state = state
        if state == "TRANSCODING":
            self.start_time = time.time()
        elif state in ("IDLE", "ERROR"):
            self.start_time = None

    async def start(self):
        """Starts the engine state loop."""
        if self.is_running:
            return
        
        self.is_running = True
        self._shutdown_evt.clear()
        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info("Restream Engine started.")

    async def stop(self):
        """Stops the engine loop and kills active processes."""
        if not self.is_running:
            return
            
        self.is_running = False
        self._shutdown_evt.set()
        
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
            
        await self.transcoder.stop()
        self.set_state("IDLE")
        logger.info("Restream Engine stopped.")

    async def force_refresh(self):
        """Forcibly clears cached credentials/URL and restarts the sniffing cycle."""
        logger.info("Forcing engine stream refresh...")
        # Clear cache file
        cache_file = self.config.cache_dir / "stream_url.txt"
        if cache_file.exists():
            try:
                cache_file.unlink()
            except Exception as e:
                logger.warning(f"Could not delete stream url cache file: {e}")
        
        self.active_url = None
        await self.transcoder.stop()
        
        # If the loop is running, we cancel the current wait/sleep and let the loop continue
        if self.is_running and self._loop_task:
            # We don't want to stop the engine, just restart the loop cycle.
            # Stopping and starting achieves this safely.
            await self.stop()
            await self.start()

    async def _run_loop(self):
        """Main orchestrator loop."""
        retry_delay = 5.0
        
        while self.is_running:
            try:
                # 1. Validation check
                if not self.config.is_valid():
                    self.error_message = "Credentials or Event URL not configured. Edit settings to continue."
                    self.set_state("ERROR")
                    await asyncio.sleep(5)
                    continue

                # 2. Check for cached stream URL
                cache_file = self.config.cache_dir / "stream_url.txt"
                if not self.active_url and cache_file.exists():
                    try:
                        self.active_url = cache_file.read_text().strip()
                        logger.info("Loaded stream URL from local cache.")
                    except Exception as e:
                        logger.warning(f"Failed to read cache file: {e}")

                # 3. Stream acquisition phase
                if not self.active_url:
                    self.set_state("SNIFFING")
                    self.error_message = None
                    try:
                        self.active_url = await sniff_stream_url(self.config)
                    except Exception as e:
                        self.error_message = f"Browser automation error: {str(e)}"
                        self.set_state("ERROR")
                        logger.error(f"Failed to acquire stream: {e}")
                        # Exponential backoff up to 60s
                        await asyncio.sleep(retry_delay)
                        retry_delay = min(retry_delay * 1.5, 60.0)
                        continue

                # Reset retry delay on successful Sniffing
                retry_delay = 5.0

                # 4. Transcoding phase
                self.set_state("TRANSCODING")
                self.error_message = None
                output_file = self.config.media_dir / "local.m3u8"
                
                transcode_start_time = time.time()
                
                try:
                    await self.transcoder.start(self.active_url, output_file)
                    exit_code = await self.transcoder.wait()
                    
                    # Check if FFmpeg failed immediately (likely due to expired URL)
                    duration = time.time() - transcode_start_time
                    if duration < 10.0 and self.is_running:
                        logger.warning(f"FFmpeg terminated quickly (in {duration:.1f}s). Stream URL likely expired.")
                        self.active_url = None
                        if cache_file.exists():
                            cache_file.unlink(missing_ok=True)
                        self.error_message = "Stream link expired or failed to transcode. Recapturing..."
                        self.set_state("ERROR")
                        await asyncio.sleep(5)
                    else:
                        logger.info(f"FFmpeg process ended after {duration:.1f}s.")
                        if self.is_running:
                            # Let's wait a moment and try again.
                            await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Error during transcoding process: {e}")
                    self.error_message = f"Transcoder failed: {str(e)}"
                    self.set_state("ERROR")
                    await asyncio.sleep(5)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.critical(f"Critical error in engine loop: {e}", exc_info=True)
                self.error_message = f"System error: {str(e)}"
                self.set_state("ERROR")
                await asyncio.sleep(10)

    def get_status(self) -> dict:
        uptime = 0
        if self.start_time:
            uptime = int(time.time() - self.start_time)
            
        return {
            "state": self.state,
            "is_running": self.is_running,
            "uptime": uptime
        }
