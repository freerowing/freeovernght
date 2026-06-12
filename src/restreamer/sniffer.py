import asyncio
import logging
from urllib.parse import urljoin
import httpx
from typing import Any
from playwright.async_api import async_playwright
from config import Config

logger = logging.getLogger("restreamer.sniffer")

def _parse_variant_line(line: str) -> tuple[int, str]:
    bandwidth = 0
    resolution = ""
    parts = line[len("#EXT-X-STREAM-INF:"):].split(",")
    for part in parts:
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip().upper()
            v = v.strip().strip('"')
            if k == "BANDWIDTH":
                try:
                    bandwidth = int(v)
                except ValueError:
                    pass
            elif k == "RESOLUTION":
                resolution = v.lower()
    return bandwidth, resolution

def _select_best_variant(variants: list[tuple[int, str, str]]) -> str:
    variants.sort(key=lambda x: x[0], reverse=True)
    # Try to find a 1080p resolution variant
    for bw, res, v_url in variants:
        if "1080" in res or "1920x1080" in res:
            logger.info(f"🎯 Selected 1080p variant: {v_url} (Bandwidth: {bw}, Resolution: {res})")
            return v_url
    # Fallback to absolute highest bandwidth
    logger.info(f"🎯 Selected highest quality variant: {variants[0][2]} (Bandwidth: {variants[0][0]}, Resolution: {variants[0][1]})")
    return variants[0][2]

async def resolve_highest_quality_stream(url: str) -> str:
    """Parses a master HLS playlist and extracts the highest quality variant URL."""
    if ".m3u8" not in url:
        return url

    logger.info(f"Parsing stream playlist: {url}")
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            resp = await client.get(url)
            if "#EXT-X-STREAM-INF" not in resp.text:
                return url

            lines = resp.text.splitlines()
            variants: list[tuple[int, str, str]] = []

            for i, line in enumerate(lines):
                if not line.startswith("#EXT-X-STREAM-INF"):
                    continue

                bandwidth, resolution = _parse_variant_line(line)

                # Next line is the URL
                if i + 1 < len(lines):
                    variant_url = lines[i+1].strip()
                    if variant_url and not variant_url.startswith("#"):
                        if not variant_url.startswith("http"):
                            variant_url = urljoin(url, variant_url)
                        variants.append((bandwidth, resolution, variant_url))

            if variants:
                return _select_best_variant(variants)

    except Exception as e:
        logger.warning(f"⚠️ Exception during quality resolution: {e}")
    return url


async def _setup_browser(p: Any, config: Config) -> Any:
    logger.info(f"Launching browser (Headless: {config.headless})...")

    launch_kwargs = {
        "headless": config.headless,
        "args": [
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--no-first-run",
            "--no-zygote",
            "--single-process",
            "--autoplay-policy=no-user-gesture-required",
            "--mute-audio"
        ]
    }

    if config.browser_executable_path:
        launch_kwargs["executable_path"] = config.browser_executable_path

    return await p.chromium.launch(**launch_kwargs)

async def _attempt_direct_navigation(page: Any, config: Config, cookies_path: Any, captured_url: list[str | None]) -> bool:
    if not cookies_path.exists():
        return False
    try:
        logger.info(f"Attempting direct navigation to Event URL: {config.event_url}")
        await page.goto(config.event_url, timeout=20000, wait_until="domcontentloaded")

        current_url = page.url
        if "login" in current_url.lower() or "auth" in current_url.lower():
            logger.info("Session expired (redirected to auth). Proceeding to full login...")
        elif await page.locator('input[type="email"]').is_visible():
            logger.info("Session expired (login email input detected on page). Proceeding to full login...")
        else:
            logger.info("Event page loaded, waiting to capture stream URL...")
            for _ in range(10):
                if captured_url[0]:
                    return True
                await asyncio.sleep(1)
    except Exception as e:
        logger.warning(f"Direct navigation with cached cookies failed: {e}")
    return False

async def _perform_full_login(page: Any, context: Any, config: Config, cookies_path: Any) -> None:
    logger.info("Running full login authentication sequence...")
    await page.goto(config.login_url, timeout=30000, wait_until="domcontentloaded")

    current_url = page.url
    if "login" not in current_url.lower() and "auth" not in current_url.lower():
        logger.info("Already logged in (redirected away from login page). Saving cookies...")
        await context.storage_state(path=str(cookies_path))
    else:
        logger.info("Waiting for login form fields...")
        email_selector = 'input[type="email"]'
        password_selector = 'input[type="password"]'  # nosec B105
        await page.wait_for_selector(email_selector, timeout=15000)

        logger.info("Entering email...")
        email_field = page.locator(email_selector)
        await email_field.click()
        await email_field.fill("")
        await email_field.press_sequentially(config.email, delay=30)

        logger.info("Entering password...")
        password_field = page.locator(password_selector)
        await password_field.click()
        await password_field.fill("")
        await password_field.press_sequentially(config.password, delay=30)

        await asyncio.sleep(0.5)

        submit_selector = 'button[type="submit"]'
        try:
            await page.wait_for_selector('button[type="submit"]:not([disabled])', timeout=5000)
            logger.info("Submit button is enabled.")
        except Exception:
            logger.warning("Submit button remained disabled. Attempting click with force...")

        logger.info("Submitting credentials...")
        await page.click(submit_selector, force=True)

        try:
            logger.info("Waiting for redirect away from login page...")
            await page.wait_for_url(lambda url: "auth/login" not in url.lower() and "login" not in url.lower(), timeout=15000)
            logger.info("Redirect completed successfully.")
        except Exception as e:
            logger.warning(f"URL did not redirect away from login within timeout: {e}")

        await page.wait_for_load_state("networkidle", timeout=15000)
        await asyncio.sleep(1)

        await context.storage_state(path=str(cookies_path))
        logger.info(f"Session cookies successfully saved to {cookies_path}")

async def _wait_for_stream_url(captured_url: list[str | None], page: Any, context: Any, config: Config, cookies_path: Any) -> str:
    session_valid = await _attempt_direct_navigation(page, config, cookies_path, captured_url)

    if not session_valid:
        try:
            await _perform_full_login(page, context, config, cookies_path)
        except Exception as e:
            logger.error(f"❌ Authentication phase failed: {e}")
            raise

        try:
            logger.info(f"Navigating to Event URL: {config.event_url}")
            await page.goto(config.event_url, timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            logger.error(f"❌ Event navigation failed: {e}")
            raise

    for _ in range(30):
        if captured_url[0]:
            break
        await asyncio.sleep(1)

    if not captured_url[0]:
        raise TimeoutError("Failed to intercept any .m3u8 stream request within 30 seconds.")

    return captured_url[0]

async def sniff_stream_url(config: Config) -> str:
    """Uses Playwright to log in and sniff the livestream .m3u8 URL, caching cookies for session reuse."""
    if not config.is_valid():
        raise ValueError("Configuration credentials or Event URL are missing.")

    logger.info("🤖 Starting headless browser automation...")
    cookies_path = config.cookies_cache

    from typing import Any
    async with async_playwright() as p:
        browser = await _setup_browser(p, config)

        try:
            user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
            context_args: dict[str, Any] = {
                "viewport": {"width": 1280, "height": 720},
                "user_agent": user_agent
            }
            if cookies_path.exists():
                logger.info("Loading session state/cookies from cache...")
                context_args["storage_state"] = str(cookies_path)

            context = await browser.new_context(**context_args)
            page = await context.new_page()

            captured_url: list[str | None] = [None]

            async def handle_request(req: Any) -> None:
                url = req.url
                if ".m3u8" in url and not captured_url[0]:
                    captured_url[0] = url
                    logger.info(f"🔗 Sniffed HLS stream URL candidate: {url}")

            page.on("request", handle_request)

            raw_url = await _wait_for_stream_url(captured_url, page, context, config, cookies_path)
            final_url = await resolve_highest_quality_stream(raw_url)

            cache_file = config.stream_url_cache
            cache_file.write_text(final_url)
            logger.info(f"Successfully cached stream URL to {cache_file}")

            return final_url
        finally:
            await browser.close()
            logger.info("🤖 Headless browser closed.")
