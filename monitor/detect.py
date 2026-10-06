"""Find which ATS a company uses, starting from its domain or careers-page URL.

Fetches the homepage, follows links that look like a careers page (plus a few common
paths), and scans each page for ATS fingerprints. Run standalone to debug:
    python -m monitor.detect valens.com wiliot.com
"""
from __future__ import annotations

import re
import sys
import json
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from .adapters import comeet

SIGNATURES = [  # (ats, regex, board builder from match)
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([\w-]+)"),
     lambda m: m.group(1)),
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([\w-]+)"), lambda m: m.group(1)),
    ("lever", re.compile(r"jobs\.eu\.lever\.co/([\w.-]+)"), lambda m: f"eu:{m.group(1)}"),
    ("lever", re.compile(r"jobs\.lever\.co/([\w.-]+)"), lambda m: m.group(1)),
    ("workday", re.compile(r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)"),
     lambda m: f"{m.group(1)}/{m.group(2)}/{m.group(3)}"),
    ("smartrecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([\w-]+)"), lambda m: m.group(1)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([\w.-]+)"), lambda m: m.group(1)),
    ("workable", re.compile(r"apply\.workable\.com/([\w-]+)"), lambda m: m.group(1)),
    ("eightfold", re.compile(r"([\w-]+)\.eightfold\.ai"), lambda m: m.group(1)),
    ("bamboohr", re.compile(r"([\w-]+)\.bamboohr\.com/(?:careers|jobs)"), lambda m: m.group(1)),
    ("teamtailor", re.compile(r"([\w-]+)\.teamtailor\.com"), lambda m: m.group(1)),
    ("recruitee", re.compile(r"([\w-]+)\.recruitee\.com"), lambda m: m.group(1)),
    ("breezy", re.compile(r"([\w-]+)\.breezy\.hr"), lambda m: m.group(1)),
]
IGNORE_BOARDS = {"embed", "js", "v1", "jobs", "www", "api", "assets", "static", "cdn"}
CAREER = re.compile(r"career|(?:^|[/ -])jobs?(?:$|[/ ?-])|join[- ]us|open[- ]positions|"
                    r"positions|we're hiring|קריירה|משרות|דרושים|הצטרפו", re.I)
IRRELEVANT = re.compile(r"newsletter|subscribe|partner-questionnaire|/feed/?$", re.I)
ASSET = re.compile(r"\.(?:css|png|jpe?g|gif|svg|ico|woff2?|ttf|pdf|zip)$", re.I)
COMMON_PATHS = ["/careers", "/careers/", "/career", "/company/careers", "/about/careers",
                "/about-us/careers", "/en/careers", "/jobs", "/join-us", "/open-positions",
                "/careers/open-positions"]


def scan(page: str, url: str = "") -> tuple[str, str] | None:
    board, _ = comeet.board_from_html(page)
    if board:
        return "comeet", board
    boot = re.search(r'<code\b[^>]*\bid=["\x27]pcsx-data["\x27][^>]*>(.*?)</code>', page, re.S)
    if boot and url:
        try:
            domain = json.loads(unescape(boot.group(1))).get("domain")
            if domain:
                return "eightfold", f"{urlparse(url).netloc}|{domain}"
        except (ValueError, AttributeError):
            pass
    for ats, rx, build in SIGNATURES:
        for m in rx.finditer(page):
            b = build(m)
            if b.split("/")[0].split(":")[-1].lower() not in IGNORE_BOARDS:
                return ats, b
    return None


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str]] = []
        self.anchor = None
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a":
            self.anchor, self.text = a.get("href"), []
        elif tag in {"iframe", "script"} and a.get("src"):
            self.links.append((tag, a["src"], ""))

    def handle_data(self, data):
        if self.anchor:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor:
            self.links.append(("a", self.anchor, " ".join(self.text)))
            self.anchor = None


def _identity(url: str) -> tuple[str, str, str]:
    u = urlparse(url)
    return ((u.hostname or "").lower().removeprefix("www."), u.path.rstrip("/"), u.query)


def _candidates(base: str, page: str, common: bool = True) -> list[str]:
    host = _identity(base)[0]
    parser = _Links()
    parser.feed(page)
    urls: list[tuple[int, str]] = []
    for tag, href, label in parser.links:
        u = urljoin(base, href.strip())
        parts = urlparse(u)
        remote = (parts.hostname or "").lower().removeprefix("www.")
        same_site = remote == host or remote.endswith("." + host)
        hosted = bool(comeet.HOSTED_RE.search(u))
        if parts.scheme not in {"http", "https"} or ASSET.search(parts.path) or IRRELEVANT.search(u + " " + label):
            continue
        if re.match(r"^/(?:de|fr|es|zh-hans|ja|ko)/", parts.path, re.I):
            continue
        if tag == "script":
            if "comeet" in page.lower() and (same_site or remote in {"comeet.co", "comeet.com"}):
                # SDKs contain no company settings. Only inspect integration/config scripts.
                if "/careers-api/api.js" not in u and re.search(r"comeet|widget|integration|config|main\.|scripts\.", u, re.I):
                    urls.append((2, u))
        elif hosted or (same_site and (tag == "iframe" or CAREER.search(parts.path + " " + label))):
            urls.append((0 if hosted or re.search(comeet.UID, parts.path) else 1, u))
    if common:
        urls += [(10, urljoin(base, p)) for p in COMMON_PATHS]
    seen, out = set(), []
    for _, u in sorted(urls, key=lambda item: item[0]):
        key = _identity(u)
        if key not in seen:
            seen.add(key)
            out.append(u)
    return out


def detect(http, target: str, max_pages: int = 12, trace: list | None = None) -> tuple[str, str] | None:
    """target: a domain ("valens.com") or a full careers URL.
    trace (optional) collects "status url" lines explaining what was tried."""
    trace = trace if trace is not None else []
    start = target if target.startswith("http") else f"https://{target}"
    queue, visited, blocked = [start], set(), set()
    scripts = 0
    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        key = _identity(url)
        if key in visited or key[0] in blocked:
            continue
        is_script = urlparse(url).path.endswith(".js")
        if is_script:
            if scripts >= 3:
                continue
            scripts += 1
        visited.add(key)
        try:
            page = http.get_text(url)
        except Exception as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            trace.append(f"{code or type(e).__name__} {url}")
            if code in {403, 429}:
                blocked.add(key[0])   # don't hammer more paths on the same blocked host
            if url == start:
                queue += _candidates(start, "")
            continue
        hint = " comeet?" if "comeet" in page.lower() else ""
        trace.append(f"ok {url}{hint}")
        found = scan(page, url)
        if found:
            return found
        # A hosted page can carry only the token; the company UID is in its URL.
        hosted_match = comeet.HOSTED_RE.search(url)
        tok = comeet.TOKEN_RE.search(comeet.normalize(page))
        if hosted_match and tok:
            return "comeet", f"{hosted_match.group(2)}|{tok.group(1)}"
        _, hosted = comeet.board_from_html(page)
        if hosted:
            queue.insert(0, hosted)
        if not is_script:
            queue[0:0] = _candidates(url, page, common=url == start)
    return None


if __name__ == "__main__":
    from .http import Http
    h = Http()
    for t in sys.argv[1:]:
        print(f"{t:30} -> {detect(h, t)}")
