import asyncio
import logging
from urllib.parse import urljoin
import httpx
from playwright.async_api import async_playwright
from config import Config

logger = logging.getLogger("restreamer.sniffer")

async def resolve_highest_quality_stream(url: str) -> str:
    """Parses a master HLS playlist and extracts the highest quality variant URL."""
    if not (".m3u8" in url):
        return url
        
    logger.info(f"Parsing stream playlist: {url}")
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            resp = await client.get(url)
            if "#EXT-X-STREAM-INF" in resp.text:
                lines = resp.text.splitlines()
                variants = []
                for i, line in enumerate(lines):
                    if line.startswith("#EXT-X-STREAM-INF"):
                        bandwidth = 0
                        resolution = ""
                        # Extract bandwidth and resolution
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
                                    
                        # Next line is the URL
                        if i + 1 < len(lines):
                            variant_url = lines[i+1].strip()
                            if variant_url and not variant_url.startswith("#"):
                                if not variant_url.startswith("http"):
                                    variant_url = urljoin(url, variant_url)
                                variants.append((bandwidth, resolution, variant_url))
                
                if variants:
                    # Sort by bandwidth descending
                    variants.sort(key=lambda x: x[0], reverse=True)
                    # Try to find a 1080p resolution variant
                    for bw, res, v_url in variants:
                        if "1080" in res or "1920x1080" in res:
                            logger.info(f"🎯 Selected 1080p variant: {v_url} (Bandwidth: {bw}, Resolution: {res})")
                            return v_url
                    # Fallback to absolute highest bandwidth
                    logger.info(f"🎯 Selected highest quality variant: {variants[0][2]} (Bandwidth: {variants[0][0]}, Resolution: {variants[0][1]})")
                    return variants[0][2]
    except Exception as e:
        logger.warning(f"⚠️ Exception during quality resolution: {e}")
    return url

async def sniff_stream_url(config: Config) -> str:
    """Uses Playwright to log in and sniff the livestream .m3u8 URL."""
    if not config.is_valid():
        raise ValueError("Configuration credentials or Event URL are missing.")

    logger.info("🤖 Starting headless browser automation...")
    
    async with async_playwright() as p:
        # Launch Chromium headless
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        captured_url = None
        
        # Intercept network requests
        async def handle_request(req):
            nonlocal captured_url
            url = req.url
            if ".m3u8" in url and not captured_url:
                # Avoid capturing sub-variants directly if possible, catch master/index playlist
                # Usually overnght serves a master list first or directly serves stream chunks
                captured_url = url
                logger.info(f"🔗 Sniffed HLS stream URL candidate: {url}")

        page.on("request", handle_request)
        
        # 1. Login Phase
        logger.info(f"Navigating to login page: {config.login_url}")
        try:
            await page.goto(config.login_url, timeout=30000, wait_until="domcontentloaded")
            
            # Wait for email input
            logger.info("Waiting for login form fields...")
            email_selector = 'input[type="email"]'
            password_selector = 'input[type="password"]'
            await page.wait_for_selector(email_selector, timeout=15000)
            
            # Type email character by character to trigger frontend validations
            logger.info("Entering email...")
            email_field = page.locator(email_selector)
            await email_field.click()
            await email_field.fill("")
            await email_field.press_sequentially(config.email, delay=30)
            
            # Type password character by character
            logger.info("Entering password...")
            password_field = page.locator(password_selector)
            await password_field.click()
            await password_field.fill("")
            await password_field.press_sequentially(config.password, delay=30)
            
            # Brief delay to allow field change handlers to process
            await asyncio.sleep(0.5)
            
            # Wait up to 5s for submit button to enable
            submit_selector = 'button[type="submit"]'
            try:
                await page.wait_for_selector('button[type="submit"]:not([disabled])', timeout=5000)
                logger.info("Submit button is enabled.")
            except Exception:
                logger.warning("Submit button remained disabled. Attempting click with force...")
                
            logger.info("Submitting credentials...")
            await page.click(submit_selector, force=True)
            
            # Wait for navigation / state load
            await page.wait_for_load_state("networkidle", timeout=15000)
            logger.info("Authentication complete. Navigating to event URL...")
        except Exception as e:
            logger.error(f"❌ Authentication phase failed: {e}")
            await browser.close()
            raise
            
        # 2. Event Sniffing Phase
        try:
            logger.info(f"Navigating to Event URL: {config.event_url}")
            await page.goto(config.event_url, timeout=30000, wait_until="domcontentloaded")
            
            # Wait to capture the .m3u8 url
            for seconds in range(30):
                if captured_url:
                    break
                await asyncio.sleep(1)
                
            if not captured_url:
                raise TimeoutError("Failed to intercept any .m3u8 stream request within 30 seconds.")
                
            # Resolve highest quality variant if it is a master playlist
            final_url = await resolve_highest_quality_stream(captured_url)
            
            # Write to cache file for safety
            cache_file = config.cache_dir / "stream_url.txt"
            cache_file.write_text(final_url)
            logger.info(f"Successfully cached stream URL to {cache_file}")
            
            return final_url
        except Exception as e:
            logger.error(f"❌ Event sniffing phase failed: {e}")
            raise
        finally:
            await browser.close()
            logger.info("🤖 Headless browser closed.")
