import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("restreamer.transcoder")

class Transcoder:
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None
        self.stream_url: Optional[str] = None
        self.output_path: Optional[Path] = None
        self._read_task: Optional[asyncio.Task] = None
        self.is_active = False

    async def start(self, stream_url: str, output_path: Path):
        if self.process:
            await self.stop()

        self.stream_url = stream_url
        self.output_path = output_path
        self.is_active = True

        # Ensure output directory exists
        self.output_path.parent.mkdir(exist_ok=True, parents=True)

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel", "warning",  # Suppresses frame-by-frame status lines to save CPU
            "-reconnect", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-i", stream_url,
            "-c", "copy",
            "-hls_time", "4",
            "-hls_list_size", "5",
            "-hls_flags", "delete_segments",
            str(output_path)
        ]

        logger.info(f"Starting FFmpeg: {' '.join(cmd)}")
        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self._read_task = asyncio.create_task(self._read_logs())
        except Exception as e:
            self.is_active = False
            self.process = None
            logger.error(f"Failed to start FFmpeg process: {e}")
            raise

    async def _read_logs(self):
        """Reads FFmpeg stderr/stdout output logs line-by-line asynchronously."""
        if not self.process or not self.process.stderr:
            return

        try:
            while True:
                line_bytes = await self.process.stderr.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if line:
                    # Status messages can be noisy; write to debug. Normal updates to info.
                    if any(x in line for x in ["speed=", "frame=", "Opening", "size="]):
                        logger.debug(f"[FFmpeg] {line}")
                    else:
                        logger.info(f"[FFmpeg] {line}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error reading FFmpeg stream logs: {e}")

    async def wait(self) -> int:
        """Wait for the process to exit and returns the exit code."""
        if not self.process:
            return 0
        code = await self.process.wait()
        self.is_active = False
        return code

    async def stop(self):
        """Stops the FFmpeg process gracefully."""
        self.is_active = False
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None

        if self.process:
            logger.info("Terminating FFmpeg process...")
            try:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("FFmpeg SIGTERM timed out. Forcing SIGKILL...")
                    self.process.kill()
                    await self.process.wait()
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.error(f"Error while terminating FFmpeg: {e}")
            finally:
                self.process = None
                
        self.stream_url = None
        self.output_path = None
        logger.info("FFmpeg process terminated successfully.")
