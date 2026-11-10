"""Polite HTTP helper for public pages only. No login, no captcha bypass."""
from __future__ import annotations

import random
import time
import urllib.error
import urllib.request
from typing import Optional

USER_AGENT = (
    "ThailandGasStationSiteFinder/1.0 "
    "(+https://github.com/piyaster11/thailand-gas-station-site-finder; "
    "open research crawler; respects robots.txt; contact via GitHub issues)"
)

# Sites that returned a challenge, 401, or block during the initial source check.
BLOCKED_HOST_NOTES = {
    "www.ddproperty.com": "Cloudflare managed challenge (403) — skipped, no captcha bypass.",
    "ddproperty.com": "Cloudflare managed challenge (403) — skipped, no captcha bypass.",
    "www.hipflat.co.th": "HTTP 401 Access Denied — skipped.",
    "www.baania.com": "Cloudflare IP block (403) — skipped.",
}


class FetchResult:
    def __init__(self, url: str, status: int, body: str, final_url: str, error: Optional[str] = None):
        self.url = url
        self.status = status
        self.body = body
        self.final_url = final_url
        self.error = error

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and not self._looks_like_challenge()

    def _looks_like_challenge(self) -> bool:
        head = (self.body or "")[:2500].lower()
        if self.status in (401, 403, 429, 503) and any(
            x in head for x in ("just a moment", "cf-mitigated", "attention required", "access denied", "captcha")
        ):
            return True
        if "just a moment..." in head and "cloudflare" in head:
            return True
        if "sorry, you have been blocked" in head:
            return True
        return False

    @property
    def blocked(self) -> bool:
        return self._looks_like_challenge() or self.status in (401, 403)


def fetch(url: str, timeout: int = 35, retries: int = 3, delay: float = 1.25) -> FetchResult:
    """GET a public URL with a delay, retries on 429/5xx, and no cookie/login jar tricks."""
    last: Optional[FetchResult] = None
    for attempt in range(retries):
        if delay:
            # Small jitter so scheduled runs don't pulse in lockstep.
            time.sleep(delay + random.uniform(0, 0.35))
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
                "Accept-Language": "en-US,en;q=0.8,th;q=0.6",
                "Accept-Encoding": "identity",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                charset = resp.headers.get_content_charset() or "utf-8"
                try:
                    body = raw.decode(charset, "replace")
                except LookupError:
                    body = raw.decode("utf-8", "replace")
                result = FetchResult(url, getattr(resp, "status", 200) or 200, body, resp.geturl())
        except urllib.error.HTTPError as e:
            raw = e.read() or b""
            body = raw.decode("utf-8", "replace")
            result = FetchResult(url, e.code, body, url, error=str(e))
        except Exception as e:
            result = FetchResult(url, 0, "", url, error=f"{type(e).__name__}: {e}")

        last = result
        if result.ok:
            return result
        if result.blocked:
            # Do not retry a captcha / access-denied page.
            return result
        if result.status in (404, 410):
            return result
        # retry 429 / 5xx / network
        time.sleep(min(8, 2 ** attempt))
    return last or FetchResult(url, 0, "", url, error="unknown")
