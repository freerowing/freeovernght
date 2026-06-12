from pathlib import Path
from config import Config

def test_config_initialization(tmp_path: Path):
    config = Config(tmp_path)
    assert config.root_dir == tmp_path
    assert config.env_path == tmp_path / ".env"
    assert config.media_dir == tmp_path / "media"

def test_config_save_load(tmp_path: Path):
    config = Config(tmp_path)
    config.save("test@example.com", "password123", "http://event.url", 8080)

    config2 = Config(tmp_path)
    assert config2.email == "test@example.com"
    assert config2.password == "password123"
    assert config2.event_url == "http://event.url"
    assert config2.port == 8080
    assert config2.is_valid() is True
