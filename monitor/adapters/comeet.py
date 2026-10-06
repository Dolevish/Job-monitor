"""Comeet careers API (used by many Israeli companies, often embedded in their own site).

board = "<companyUID>|<token>". Both are public: Comeet embeds them in the careers page
script, and the hosted page www.comeet.com/jobs/<slug>/<uid> carries the token too.
Use resolve() to turn a careers-page URL into a board.
"""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qs

from ..http import html_to_text
from ..models import Job

UID = r"[0-9A-Za-z]{2}\.[0-9A-Za-z]{3}"
TOKEN_RE = re.compile(r"(?<![\w-])[\"']?(?:data-|comeet_)?token[\"']?\s*[:=]\s*[\"']([A-Za-z0-9_-]{20,})[\"']", re.I)
UID_RE = re.compile(rf"(?<![\w-])[\"']?(?:(?:data-)?company[-_]?uid|comeet_uid)[\"']?\s*[:=]\s*[\"']({UID})[\"']", re.I)
API_RE = re.compile(rf"careers-api/2\.0/company/({UID})/positions\?([^\s\"'<>]+)")
HOSTED_RE = re.compile(rf"comeet\.com?/jobs/([\w.-]+)/({UID})\b", re.I)


def normalize(page: str) -> str:
    """Handle HTML entities and URL/quote escaping in serialized widget settings."""
    return html.unescape(page).replace(r"\/", "/").replace(r'\"', '"').replace(r"\'", "'")


def board_from_html(page: str) -> tuple[str | None, str | None]:
    """Return (board, hosted_url). board is "uid|token" if both are on the page."""
    page = normalize(page)
    for m in API_RE.finditer(page):
        token = parse_qs(m.group(2)).get("token", [""])[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{20,}", token):
            return f"{m.group(1)}|{token}", None
    tok, uid = TOKEN_RE.search(page), UID_RE.search(page)
    if tok and uid:
        return f"{uid.group(1)}|{tok.group(1)}", None
    h = HOSTED_RE.search(page)
    if h:
        return None, f"https://www.comeet.com/jobs/{h.group(1)}/{h.group(2)}"
    return None, None


def resolve(http, url: str) -> str | None:
    page = http.get_text(url)
    board, hosted = board_from_html(page)
    if board or not hosted:
        return board
    tok = TOKEN_RE.search(normalize(http.get_text(hosted)))
    return f"{HOSTED_RE.search(hosted).group(2)}|{tok.group(1)}" if tok else None


def fetch(http, board: str, company: str) -> list[Job]:
    uid, token = board.split("|", 1)
    data = http.get_json(f"https://www.comeet.co/careers-api/2.0/company/{uid}/positions",
                         {"token": token, "details": "true"})
    jobs = []
    for p in data:
        loc = p.get("location") or {}
        country = (loc.get("country") or "").upper()
        where = ", ".join(x for x in [loc.get("city") or loc.get("name"),
                                      "Israel" if country == "IL" else country] if x)
        desc = "".join(f"<h3>{d.get('name', '')}:</h3>{d.get('value', '')}"
                       for d in p.get("details") or [] if d.get("value"))
        jobs.append(Job(
            source=f"comeet:{uid}", job_id=p["uid"], company=company,
            title=(p.get("name") or "").strip(),
            url=p.get("url_active_page") or p.get("url_comeet_hosted_page", ""),
            location=where, posted=p.get("time_updated", ""), description=html_to_text(desc),
        ))
    return jobs
