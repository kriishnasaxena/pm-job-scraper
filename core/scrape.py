"""Thin helpers around Scrapling so every site scraper works the same way.

Adaptive selectors: the first time a selector matches, Scrapling saves a
fingerprint of the matched elements into ADAPTIVE_DB. If the site later
renames its CSS classes and the selector stops matching, Scrapling uses
that fingerprint to find the same elements again. The GitHub workflow
caches ADAPTIVE_DB between runs so this memory survives.
"""
import os
import time

from scrapling.fetchers import Fetcher
from scrapling.parser import Selector

ADAPTIVE_DB = os.environ.get("SCRAPLING_DB", os.path.join("state", "scrapling_adaptive.db"))
os.makedirs(os.path.dirname(ADAPTIVE_DB) or ".", exist_ok=True)

_last_hit: dict[str, float] = {}


def _polite(url: str, delay: float):
    host = url.split("/")[2]
    wait = _last_hit.get(host, 0) + delay - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()


def get_page(url: str, delay: float = 1.5) -> Selector:
    """Fetch with Scrapling's browser-like HTTP client; return an adaptive Selector."""
    _polite(url, delay)
    resp = Fetcher.get(url, stealthy_headers=True, timeout=30, retries=2)
    if resp.status >= 400:
        raise RuntimeError(f"HTTP {resp.status} for {url}")
    return Selector(resp.body, url=url, adaptive=True,
                    storage_args={"storage_file": ADAPTIVE_DB, "url": url})


def select(page: Selector, selectors: list[str], identifier: str):
    """Try each selector; remember what matched; fall back to adaptive relocation."""
    for sel in selectors:
        found = page.css(sel, auto_save=True, identifier=identifier)
        if found:
            return list(found)
    # Nothing matched: the site probably changed. Ask Scrapling to relocate
    # using the fingerprint saved on an earlier successful run.
    found = page.css(selectors[0], adaptive=True, identifier=identifier)
    found = list(found or [])
    if len(found) == 1:
        found += list(found[0].find_similar())
    return found


def first_text(el, selectors: list[str]) -> str:
    for sel in selectors:
        hit = el.css(sel)
        if hit:
            txt = hit[0].get_all_text(strip=True)
            if txt:
                return " ".join(txt.split())
    return ""


def page_text(page: Selector, selectors: list[str]) -> str:
    for sel in selectors:
        hit = page.css(sel)
        if hit:
            txt = hit[0].get_all_text(separator="\n", strip=True)
            if txt and len(txt) > 200:
                return txt
    body = page.css("body")
    return body[0].get_all_text(separator="\n", strip=True) if body else ""


def next_data(html: str):
    """The JSON a Next.js site embeds in <script id="__NEXT_DATA__">, or None."""
    import json
    import re
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', html or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def fetch_html(url: str, cfg: dict, need_marker: str = "", browser_first: bool = False) -> str:
    """Get page HTML with Scrapling. Tries the fast HTTP Fetcher, then Scrapling's
    stealth browser (StealthyFetcher) if blocked or if `need_marker` is missing."""
    delay = cfg.get("request_delay", 1.5)
    tries = ["browser", "http"] if browser_first else ["http", "browser"]
    last_err = None
    for how in tries:
        try:
            _polite(url, delay)
            if how == "http":
                resp = Fetcher.get(url, stealthy_headers=True, timeout=30, retries=1)
            else:
                from scrapling.fetchers import StealthyFetcher
                resp = StealthyFetcher.fetch(url, headless=True, network_idle=True, timeout=60000,
                                             disable_resources=True)
            body = resp.body
            html = body.decode("utf-8", "ignore") if isinstance(body, (bytes, bytearray)) else str(body)
            if resp.status < 400 and (not need_marker or need_marker in html):
                return html
            last_err = RuntimeError(f"{how}: HTTP {resp.status}" + ("" if need_marker in html else f", no {need_marker}"))
        except Exception as e:
            last_err = e
    raise last_err or RuntimeError("fetch failed")
