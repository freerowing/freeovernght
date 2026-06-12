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
    """Uses Playwright to log in and sniff the livestream .m3u8 URL, caching cookies for session reuse."""
    if not config.is_valid():
        raise ValueError("Configuration credentials or Event URL are missing.")

    logger.info("🤖 Starting headless browser automation...")
    cookies_path = config.cache_dir / "cookies.json"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        
        # Load cached cookies if available
        context_args = {
            "viewport": {"width": 1280, "height": 720},
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        if cookies_path.exists():
            logger.info("Loading session state/cookies from cache...")
            context_args["storage_state"] = str(cookies_path)
            
        context = await browser.new_context(**context_args)
        page = await context.new_page()
        
        captured_url = None
        
        # Intercept network requests
        async def handle_request(req):
            nonlocal captured_url
            url = req.url
            if ".m3u8" in url and not captured_url:
                captured_url = url
                logger.info(f"🔗 Sniffed HLS stream URL candidate: {url}")

        page.on("request", handle_request)
        
        # Try direct navigation using cached session
        session_valid = False
        if cookies_path.exists():
            try:
                logger.info(f"Attempting direct navigation to Event URL: {config.event_url}")
                await page.goto(config.event_url, timeout=20000, wait_until="domcontentloaded")
                
                # Check if we were redirected to a login/auth page or if a login input is visible
                current_url = page.url
                if "login" in current_url.lower() or "auth" in current_url.lower():
                    logger.info("Session expired (redirected to auth). Proceeding to full login...")
                elif await page.locator('input[type="email"]').is_visible():
                    logger.info("Session expired (login email input detected on page). Proceeding to full login...")
                else:
                    # Wait up to 10 seconds to see if we capture the stream URL
                    logger.info("Event page loaded, waiting to capture stream URL...")
                    for _ in range(10):
                        if captured_url:
                            session_valid = True
                            break
                        await asyncio.sleep(1)
            except Exception as e:
                logger.warning(f"Direct navigation with cached cookies failed: {e}")

        # Perform full login flow if session is invalid or not available
        if not session_valid:
            logger.info("Running full login authentication sequence...")
            try:
                await page.goto(config.login_url, timeout=30000, wait_until="domcontentloaded")
                
                # Check if we got redirected away immediately because we are already logged in
                current_url = page.url
                if "login" not in current_url.lower() and "auth" not in current_url.lower():
                    logger.info("Already logged in (redirected away from login page). Saving cookies...")
                    await context.storage_state(path=str(cookies_path))
                else:
                    # Wait for email input
                    logger.info("Waiting for login form fields...")
                    email_selector = 'input[type="email"]'
                    password_selector = 'input[type="password"]'
                    await page.wait_for_selector(email_selector, timeout=15000)
                    
                    # Type credentials character-by-character
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
                    
                    # Wait up to 5s for submit button to enable
                    submit_selector = 'button[type="submit"]'
                    try:
                        await page.wait_for_selector('button[type="submit"]:not([disabled])', timeout=5000)
                        logger.info("Submit button is enabled.")
                    except Exception:
                        logger.warning("Submit button remained disabled. Attempting click with force...")
                        
                    logger.info("Submitting credentials...")
                    await page.click(submit_selector, force=True)
                    
                    # Wait for the URL to change to indicate successful redirect/auth completion
                    try:
                        logger.info("Waiting for redirect away from login page...")
                        await page.wait_for_url(lambda url: "auth/login" not in url.lower() and "login" not in url.lower(), timeout=15000)
                        logger.info("Redirect completed successfully.")
                    except Exception as e:
                        logger.warning(f"URL did not redirect away from login within timeout: {e}")
                    
                    # Wait for network idle to ensure cookies/tokens are set
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    await asyncio.sleep(1) # Extra buffer for cookies to write
                    
                    # Save storage state
                    await context.storage_state(path=str(cookies_path))
                    logger.info(f"Session cookies successfully saved to {cookies_path}")
                
            except Exception as e:
                logger.error(f"❌ Authentication phase failed: {e}")
                await browser.close()
                raise
                
            # Navigate to event page after login
            try:
                logger.info(f"Navigating to Event URL: {config.event_url}")
                await page.goto(config.event_url, timeout=30000, wait_until="domcontentloaded")
            except Exception as e:
                logger.error(f"❌ Event navigation failed: {e}")
                await browser.close()
                raise

        # Wait to capture the .m3u8 url if not already captured
        try:
            for seconds in range(30):
                if captured_url:
                    break
                await asyncio.sleep(1)
                
            if not captured_url:
                raise TimeoutError("Failed to intercept any .m3u8 stream request within 30 seconds.")
                
            # Resolve highest quality variant
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
