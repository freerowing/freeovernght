# Overnght Live HLS Restreamer

Welcome to the Overnght Live HLS Restreamer.

This is an automated, robust, and highly asynchronous Python application designed to extract and restream live feeds from the Overnght sports network. It works quietly in the background, logging in automatically, sniffing out the best quality stream (e.g., 1080p), transcoding it securely via FFmpeg, and hosting it seamlessly on an integrated, minimalist HLS web player.

Whether you are looking to watch a live game without interruptions or self-host your own restream server, this project provides a stable automated pipeline.

---

## Features

- **Ultra-Minimalist HLS Player**: A sleek, full-screen video player with a silent auto-reconnection loop.
- **Fully Asynchronous Core**: Built on Python's `asyncio`. The web server (FastAPI), scraper (Playwright), and transcoder (FFmpeg) all run concurrently for high performance.
- **Headless Automation**: Uses Playwright to securely authenticate and grab stream URLs in the background without browser popups.
- **Dynamic Resolution Selector**: Always grabs the absolute highest quality video available in the playlist.
- **Self-Healing**: If the stream drops or the link expires, the app automatically clears its cache, re-authenticates, and gets the video back online.
- **Modern src/ Architecture**: A clean, fully-tested (pytest), statically-typed (mypy), and production-ready codebase separated into an isolated `src/` layout.

---

## Requirements

- **Python 3.12+**
- **FFmpeg**: Must be installed globally on your system.
  - macOS: `brew install ffmpeg`
  - Debian/Ubuntu: `sudo apt install ffmpeg`

---

## Getting Started

Follow these quick steps to deploy the restreamer.

### 1. Clone the Repository
```bash
git clone https://github.com/freerowing/freeovernght.git
cd restreamer-overnght
```

### 2. Set Up Your Environment
Create a virtual environment to isolate the application dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Install Playwright Browsers
This downloads the headless Chromium browser needed to sniff the streams:
```bash
playwright install chromium
```

---

## Configuration

Provide your Overnght login details so the application can authenticate on your behalf.

1. Create a local configuration file from the template:
   ```bash
   cp .env.example .env
   ```
2. Open the `.env` file and configure your credentials:
   - `ACCOUNT_EMAIL`: Your Overnght email.
   - `ACCOUNT_PASSWORD`: Your password.
   - `EVENT_URL`: The URL of the live event you want to watch.
   - `PORT`: (Optional) Change the default web player port (default is 8080).

---

## Running the Application

### Manual Deployment
To run the server in your active terminal, execute:
```bash
python src/restreamer/restreamer.py
```
Open a browser and navigate to `http://localhost:8080` to view the stream.

### Testing
To run the comprehensive test suite and static analysis tools, execute:
```bash
pytest
```

---

## Background Service (Systemd)

To run the restreamer persistently in the background and start on boot, configure it as a systemd user service:

1. Edit the provided `restreamer.service` file and update all the `/PATH/TO/PROJECT` placeholders to match your absolute directory paths.
2. Copy the file into your user's systemd config directory:
   ```bash
   mkdir -p ~/.config/systemd/user/
   cp restreamer.service ~/.config/systemd/user/
   ```
3. Enable and start the service:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable restreamer.service
   systemctl --user start restreamer.service
   ```
4. Audit the real-time service logs:
   ```bash
   journalctl --user -u restreamer.service -f
   ```

---

## Privacy & Security

This codebase uses strict `.gitignore` configurations. Your `.env` credentials, `stream_url.txt` cache, generated `.m3u8` playlists, and video `.ts` segments will not be committed to source control. Ensure modifications respect these isolation boundaries.

> Note: Yes, AI was used in this repo, no idc. I did this yesterday without the help of AI, but to make it more user friendly had AI build a rugged script to do it.
