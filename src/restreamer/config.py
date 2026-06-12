import os
from pathlib import Path
from dotenv import load_dotenv

class Config:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.env_path = self.root_dir / ".env"
        self.email = ""
        self.password = ""  # nosec B105
        self.login_url = "https://www.overnght.com/auth/login"
        self.event_url = ""
        self.host = "127.0.0.1"
        self.port = 8080

        # Output folders
        self.media_dir = self.root_dir / "media"
        self.logs_dir = self.root_dir / "logs"
        self.cache_dir = self.root_dir / "cache"

        # Cache files
        self.stream_url_cache = self.cache_dir / "stream_url.txt"
        self.cookies_cache = self.cache_dir / "cookies.json"

        self.load()

    def load(self) -> None:
        # Ensure folders exist
        self.media_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)

        if self.env_path.exists():
            load_dotenv(self.env_path, override=True)

        self.email = os.getenv("ACCOUNT_EMAIL", "")
        self.password = os.getenv("ACCOUNT_PASSWORD", "")
        self.login_url = os.getenv("LOGIN_URL", "https://www.overnght.com/auth/login")
        self.event_url = os.getenv("EVENT_URL", "")
        self.headless = os.getenv("HEADLESS", "true").lower() == "true"
        self.host = os.getenv("HOST", "127.0.0.1")

        try:
            self.port = int(os.getenv("PORT", "8080"))
        except ValueError:
            self.port = 8080

    def save(self, email: str, password: str, event_url: str, port: int) -> None:
        content = f"""# ==============================================================================
# Overnght Live Restreamer Configuration
# ==============================================================================

# --- Overnght Platform Authentication ---
ACCOUNT_EMAIL="{email}"
ACCOUNT_PASSWORD="{password}"

# --- Target Route Navigation Endpoints ---
LOGIN_URL="{self.login_url}"
EVENT_URL="{event_url}"

# --- Local Serving Configurations ---
PORT={port}
"""
        self.env_path.write_text(content)
        self.load()

    def is_valid(self) -> bool:
        """Checks if the required credentials and event URL are provided."""
        return bool(self.email and self.password and self.event_url)
