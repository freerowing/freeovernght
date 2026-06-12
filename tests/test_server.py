from fastapi.testclient import TestClient
from pathlib import Path
from server import create_app
from config import Config
from engine import RestreamEngine

def test_server_status(tmp_path: Path):
    config = Config(tmp_path)
    engine = RestreamEngine(config)
    app = create_app(engine, config)

    with TestClient(app) as client:
        response = client.get("/api/status")
        assert response.status_code == 200

        data = response.json()
        assert "state" in data
        assert "is_running" in data
        assert data["is_running"] is False

def test_server_media_404(tmp_path: Path):
    config = Config(tmp_path)
    engine = RestreamEngine(config)
    app = create_app(engine, config)

    with TestClient(app) as client:
        # Requesting a non-existent file in media
        response = client.get("/media/playlist.m3u8")
        assert response.status_code == 404

def test_server_media_200(tmp_path: Path):
    config = Config(tmp_path)
    config.media_dir.mkdir(parents=True, exist_ok=True)
    (config.media_dir / "local.m3u8").write_text("test media content")

    engine = RestreamEngine(config)
    app = create_app(engine, config)

    with TestClient(app) as client:
        response = client.get("/media/local.m3u8")
        assert response.status_code == 200
        assert response.text == "test media content"

def test_player_dashboard_404(tmp_path: Path):
    config = Config(tmp_path)
    engine = RestreamEngine(config)
    app = create_app(engine, config)
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 404

def test_player_dashboard_200(tmp_path: Path):
    config = Config(tmp_path)
    (tmp_path / "index.html").write_text("<html></html>")
    engine = RestreamEngine(config)
    app = create_app(engine, config)
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
