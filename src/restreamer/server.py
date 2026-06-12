import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from config import Config
from engine import RestreamEngine

logger = logging.getLogger("restreamer.server")

class HLSStaticFiles(StaticFiles):
    """Custom StaticFiles server to inject optimized HLS cache and CORS headers."""
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        path = args[0]
        # Allow cross-origin requests for stream playback
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"

        # Optimize HLS caching to prevent player freezing
        if path.endswith(".m3u8"):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        elif path.endswith(".ts"):
            response.headers["Cache-Control"] = "public, max-age=86400"

        return response

def create_app(engine: RestreamEngine, config: Config) -> FastAPI:
    app = FastAPI(title="Overnght HLS Player Server", version="1.0.0")

    # Enable CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # Mount the static HLS media directory
    app.mount("/media", HLSStaticFiles(directory=str(config.media_dir)), name="media")

    @app.get("/")
    async def get_player_dashboard():
        index_path = config.root_dir / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="index.html player template not found.")
        return FileResponse(str(index_path))

    @app.get("/api/status")
    async def get_status():
        """Exposes only generic engine state and uptime. Safe to expose publicly."""
        return engine.get_status()

    return app
