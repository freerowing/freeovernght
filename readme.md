# Overnght Live HLS Restreamer Engine

An automated, robust pipeline built in Python to programmatically extract and restream live feeds from the Overnght sports network. It deploys an automated headless browser to authenticate and sniff live `.m3u8` feed parameters, parses out the premium highest-resolution video variant, runs an active `FFmpeg` proxy worker asynchronously, and hosts an integrated web HLS player.

## Features
*   **Ultra-Minimalist HLS Player**: A clean, full-viewport video player with a black background and silent background reconnection loops that automatically start playback when the stream goes live.
*   **Fully Asynchronous Core**: Built entirely on Python's `asyncio` event loop. The web server (FastAPI), scraper (Playwright), and transcoder (FFmpeg) run concurrently, facilitating high performance and clean process lifecycles.
*   **Fully Headless Automation**: Leverages Playwright to manage network analysis silently in the background without browser window popups.
*   **Dynamic Resolution Selector**: Intelligently parses master playlist manifests to force playback parameters to the absolute highest resolution variant (e.g. 1080p).
*   **Self-Healing Loop**: Automatically detects stream drops or URL expirations, clears cache, and triggers browser re-authentication without service interruptions.
*   **Zero-Exposure Layout**: Full isolation configuration decoupling system assets and secret keys away from standard version control trees.

## Requirements
*   Python 3.12+
*   FFmpeg installed on the global system path environment (`brew install ffmpeg` on macOS, `sudo apt install ffmpeg` on Debian/Ubuntu)

## Installation Workflow

1.  **Clone the Repository**
    ```bash
    git clone https://github.com
    cd restreamer-overnght
    ```

2.  **Initialize Virtual Environment**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Requirements**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Install Playwright Headless Drivers**
    ```bash
    playwright install chromium
    ```

## Local Configuration Management

1.  Create a local runtime configurations file:
    ```bash
    cp .env.example .env
    ```
2.  Open your newly minted `.env` file and insert your credentials (`ACCOUNT_EMAIL`, `ACCOUNT_PASSWORD`, `EVENT_URL`, and `PORT`).

## Service Execution Processes

### Manual Deployment Context
To test execution flows inside active shell terminal splits, run the main thread directly:
```bash
python restreamer.py
```
Open a browser viewport targeting `http://localhost:8080` to view your live stream.


### Background Systemd User Service Integration (Optional)
To setup persistence across system host reboot operations without manual interaction loops, configure a localized user manager node service tracking element.

1. Create a configuration blueprint schema inside your user service layout path:
   `nano ~/.config/systemd/user/restreamer.service`

2. Map out structural properties ensuring absolute pointers match your host directories:
    ```ini
    [Unit]
    Description=Overnght Live HLS Restreamer Daemon Service
    After=network.target

    [Service]
    Type=simple
    WorkingDirectory=/Users/your_username/path_to_project
    ExecStart=/Users/your_username/path_to_project/venv/bin/python /Users/your_username/path_to_project/restreamer.py
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=default.target
    ```

3. Initialize system operations:
    ```bash
    systemctl --user daemon-reload
    systemctl --user enable restreamer.service
    systemctl --user start restreamer.service
    ```

4. Audit real-time background log interactions:
    ```bash
    journalctl --user -u restreamer.service -f
    ```

## Development & Privacy Guidelines
This repository integrates rigorous `.gitignore` parsing structures targeting runtime data objects like caching structures (`stream_url.txt`), temporary playlist segments (`*.m3u8`, `*.ts`), and account details (`.env`). Ensure modifications to the core engine engine retain absolute environment encapsulation boundaries.
