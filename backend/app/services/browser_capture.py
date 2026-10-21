import ipaddress
import socket
from urllib.parse import urljoin, urlparse, urlunparse
from playwright.async_api import Error as BrowserError
from playwright.async_api import async_playwright

class UnsafeUrlError(ValueError):
    pass

class BrowserCaptureError(RuntimeError):
    pass

def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("Only http and https URLs are allowed.")
    if not parsed.hostname or parsed.username or parsed.password:
        raise UnsafeUrlError("URL must have a hostname and must not include credentials.")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain", "metadata.google.internal"} or host.endswith(".local"):
        raise UnsafeUrlError("Local and metadata hostnames are not allowed.")
    try:
        addresses = {ipaddress.ip_address(host)} if _is_ip(host) else {
            ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError):
        raise UnsafeUrlError("Hostname could not be resolved safely.")
    if not addresses or any(not ip.is_global for ip in addresses):
        raise UnsafeUrlError("URL resolves to a non-public IP address.")
    return url

def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False

PAGE_LIMIT = 3
_BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
_BLOCKED_TITLES = {"403 forbidden", "401 unauthorized", "429 too many requests", "access denied", "just a moment...", "attention required! | cloudflare"}
_SKIPPED_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".zip", ".css", ".js", ".mp4", ".ico", ".xml"}

def same_site(origin: str, candidate: str) -> bool:
    first = (urlparse(origin).hostname or "").lower().removeprefix("www.")
    second = (urlparse(candidate).hostname or "").lower().removeprefix("www.")
    return bool(first) and first == second

def page_key(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return parsed.scheme, host, path

def internal_page_links(origin: str, links: list) -> list[str]:
    found = []
    seen = set()
    for item in links:
        href = item.get("href") if isinstance(item, dict) else None
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(origin, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or not same_site(origin, absolute):
            continue
        if any(parsed.path.lower().endswith(suffix) for suffix in _SKIPPED_SUFFIXES):
            continue
        clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", ""))
        key = page_key(clean)
        if key in seen:
            continue
        seen.add(key)
        found.append(clean)
    return found

def blocked_page_message(status: int | None, title: str | None) -> str | None:
    if status in {401, 403, 429}:
        return f"The site returned {status} and did not show a page that can be audited."
    label = (title or "").strip().lower()
    if label in _BLOCKED_TITLES:
        return f"The site blocked the audit ({title}). It did not show a page that can be reviewed."
    return None

def browser_failure_message(exc: Exception) -> str:
    text = str(exc)
    if "Executable doesn't exist" in text or "playwright install" in text:
        return "URL capture needs Chromium. From the backend folder run: playwright install chromium"
    line = text.splitlines()[0].strip()
    return line or "The page could not be captured."

async def capture_website(url: str, viewport: str) -> dict:
    validate_public_url(url)
    dimensions = {"desktop": {"width": 1440, "height": 1000}, "mobile": {"width": 390, "height": 844}}[viewport]
    try:
        return await _capture(url, dimensions)
    except BrowserError as exc:
        raise BrowserCaptureError(browser_failure_message(exc)) from exc

async def _capture(url: str, dimensions: dict) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(viewport=dimensions, device_scale_factor=1, user_agent=_BROWSER_UA, locale="en-US")
            page = await context.new_page()
            # Recheck each requested URL. This is defense in depth, not a replacement for network egress controls.
            async def guard_route(route):
                try:
                    validate_public_url(route.request.url)
                except Exception:
                    await route.abort()
                    return
                await route.continue_()
            await page.route("**/*", guard_route)
            captured = []
            queue = [url]
            seen = set()
            while queue and len(captured) < PAGE_LIMIT:
                target = queue.pop(0)
                if page_key(target) in seen or not same_site(url, target):
                    continue
                seen.add(page_key(target))
                try:
                    validate_public_url(target)
                    shot = await _read_page(page, target)
                except BrowserCaptureError:
                    if captured:
                        continue
                    raise
                except (BrowserError, UnsafeUrlError):
                    if captured:
                        continue
                    raise
                captured.append(shot)
                seen.add(page_key(shot["final_url"]))
                if len(captured) == 1:
                    for link in internal_page_links(shot["final_url"], shot["evidence"].get("links") or []):
                        if page_key(link) not in seen:
                            queue.append(link)
                        if len(queue) >= PAGE_LIMIT * 3:
                            break
            if not captured:
                raise BrowserCaptureError("The page could not be captured.")
            evidence = {"page_count": len(captured), "pages": [item["evidence"] for item in captured]}
            return {
                "image": captured[0]["image"],
                "images": [item["image"] for item in captured],
                "page_evidence": evidence,
                "page_title": captured[0]["evidence"].get("title"),
                "final_url": captured[0]["final_url"],
            }
        finally:
            await browser.close()

async def _read_page(page, url: str) -> dict:
    response = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
    await page.locator("body").wait_for(state="visible", timeout=10000)
    await page.wait_for_timeout(1200)
    status = response.status if response is not None else None
    title = await page.title()
    blocked = blocked_page_message(status, title)
    if blocked:
        raise BrowserCaptureError(blocked)
    clip = await page.evaluate("""() => {
      const width = Math.max(1, Math.min(window.innerWidth, document.documentElement.scrollWidth || window.innerWidth));
      const height = Math.max(1, Math.min(2400, Math.max(window.innerHeight, document.documentElement.scrollHeight || window.innerHeight)));
      return { x: 0, y: 0, width, height };
    }""")
    image = await page.screenshot(type="png", clip=clip, timeout=15000)
    evidence = await page.evaluate("""() => ({
      title: document.title,
      url: location.href,
      headings: [...document.querySelectorAll('h1,h2,h3')].slice(0,40).map(e => ({tag:e.tagName,text:(e.innerText||'').trim().slice(0,200)})),
      buttons: [...document.querySelectorAll('button,[role=button],input[type=submit]')].slice(0,40).map(e => ({text:(e.innerText||e.getAttribute('aria-label')||e.value||'').trim().slice(0,160), disabled:!!e.disabled})),
      links: [...document.querySelectorAll('a[href]')].slice(0,80).map(e => ({text:(e.innerText||e.getAttribute('aria-label')||'').trim().slice(0,160), href:e.getAttribute('href')})),
      inputs: [...document.querySelectorAll('input,textarea,select')].slice(0,40).map(e => ({type:e.type||e.tagName.toLowerCase(),label:e.labels?.[0]?.innerText||e.getAttribute('aria-label')||e.placeholder||'', required:!!e.required})),
      imagesWithoutAlt: [...document.querySelectorAll('img:not([alt]), img[alt=""]')].length,
      lang: document.documentElement.lang || null
    })""")
    return {"image": image, "evidence": evidence, "final_url": page.url}
