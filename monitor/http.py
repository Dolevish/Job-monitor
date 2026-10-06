from __future__ import annotations

import html
import re
import random
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
RETRY_STATUS = {429, 500, 502, 503, 504}


def retry_delay(response, attempt: int) -> float:
    value = response.headers.get("Retry-After", "")
    try:
        delay = float(value)
    except ValueError:
        try:
            delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            delay = 2 * 2 ** attempt + random.uniform(0, 1)
    return min(30, max(0, delay))


class Http:
    """Thin requests wrapper: browser UA, timeouts, retry with backoff on 429/5xx."""

    def __init__(self, timeout: int = 25, retries: int = 3):
        self.timeout = timeout
        self.retries = retries
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,he;q=0.8"})

    def _req(self, method: str, url: str, **kw) -> requests.Response:
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                r = self.s.request(method, url, timeout=self.timeout, **kw)
                retry = r.status_code in RETRY_STATUS or (
                    r.status_code == 403 and "myworkdayjobs.com" in url)   # Workday rate-limits with 403
                if retry and attempt < self.retries - 1:
                    time.sleep(retry_delay(r, attempt))
                    continue
                r.raise_for_status()
                return r
            except (requests.ConnectionError, requests.Timeout) as e:
                last = e
                if attempt < self.retries - 1:
                    time.sleep(2 * 2 ** attempt + random.uniform(0, 1))
        raise last or RuntimeError(f"request failed: {url}")

    def get_json(self, url: str, params: dict | None = None):
        return self._req("GET", url, params=params, headers={"Accept": "application/json"}).json()

    def post_json(self, url: str, payload: dict):
        return self._req("POST", url, json=payload, headers={"Accept": "application/json"}).json()

    def get_text(self, url: str) -> str:
        return self._req("GET", url).text


_BLOCK = re.compile(r"<\s*(br|/p|/div|/li|/h\d|/tr|/ul|/ol)\b[^>]*>", re.I)
_LI = re.compile(r"<\s*li\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\u00a0]+")


def html_to_text(raw: str | None) -> str:
    """HTML (possibly entity-escaped, as Greenhouse returns it) -> plain text, one block per line."""
    if not raw:
        return ""
    s = html.unescape(raw) if "&lt;" in raw else raw
    s = re.sub(r"<(script|style)\b.*?</\1>", " ", s, flags=re.I | re.S)
    s = _LI.sub("\n• ", s)
    s = _BLOCK.sub("\n", s)
    s = html.unescape(_TAG.sub(" ", s))
    lines = (_WS.sub(" ", ln).strip() for ln in s.splitlines())
    return "\n".join(ln for ln in lines if ln)
