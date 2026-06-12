import asyncio
import logging
import signal
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
import uvicorn

from config import Config
from engine import RestreamEngine
from server import create_app

# Initialize workspace directories relative to this file
root_dir = Path(__file__).parent.absolute()
logs_dir = root_dir / "logs"
logs_dir.mkdir(exist_ok=True)

# 1. Rolling File Handler (keep last 3 log files, up to 5MB each)
file_handler = RotatingFileHandler(logs_dir / "restreamer.log", maxBytes=5*1024*1024, backupCount=3)
file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))

# 2. Standard Console Handler (stdout)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"))

# Configure Root Logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

# Set logger levels for noisy libraries
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

logger = logging.getLogger("restreamer.main")

async def main():
    logger.info("Initializing Overnght Restreamer Application...")
    
    # Load settings configuration
    config = Config(root_dir)
    
    # Initialize Core Engine Manager
    engine = RestreamEngine(config)
    
    # Setup FastAPI HTTP server
    app = create_app(engine, config)
    
    # Auto-start engine if configuration is already valid
    if config.is_valid():
        logger.info("Found valid environment credentials. Auto-starting restreamer engine...")
        await engine.start()
    else:
        logger.warning("Credentials or event URL missing in .env file.")

    # Configure Uvicorn server to run in our async loop
    uvicorn_config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=config.port,
        log_config=None,  # We handle all logging
        loop="asyncio"
    )
    server = uvicorn.Server(uvicorn_config)

    # Signal trapping for graceful shutdowns (SIGINT, SIGTERM)
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def handle_signal():
        logger.info("Shutdown signal captured. Initiating clean exit...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            # Handles OS boundaries if required
            pass

    # Start FastAPI as an asynchronous background task
    server_task = asyncio.create_task(server.serve())

    # Block main thread until signal or exit event is triggered
    await stop_event.wait()

    # Graceful shutdown pipeline
    logger.info("Stopping Restreamer Engine & Subprocesses...")
    await engine.stop()
    
    logger.info("Shutting down Web Server...")
    server.should_exit = True
    try:
        await asyncio.wait_for(server_task, timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning("Uvicorn server failed to shut down in time. Cancelling task.")
        server_task.cancel()
        
    logger.info("All services shut down cleanly. System terminated.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass