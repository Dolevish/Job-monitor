"""Find which ATS a company uses, starting from its domain or careers-page URL.

Fetches the homepage, follows links that look like a careers page (plus a few common
paths), and scans each page for ATS fingerprints. Run standalone to debug:
    python -m monitor.detect valens.com wiliot.com
"""
from __future__ import annotations

import re
import sys
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
CAREER_LINK = re.compile(r"""href=["']([^"'#]+)["'][^>]*>(?:(?!</a>).){0,200}?"""
                         r"""(?:career|jobs|join us|join our|open positions|we're hiring|"""
                         r"""קריירה|משרות|דרושים|הצטרפו)""", re.I | re.S)
CAREER_HREF = re.compile(r"""href=["']([^"'#]*(?:career|jobs|join-us|positions)[^"'#]*)["']""", re.I)
POSITION_HREF = re.compile(rf"""href=["']([^"']*(?:id=|/){comeet.UID})(?=["'/?&])""")
COMMON_PATHS = ["/careers", "/careers/", "/career", "/company/careers", "/about/careers",
                "/about-us/careers", "/en/careers", "/jobs", "/join-us", "/open-positions",
                "/careers/open-positions"]


def scan(page: str) -> tuple[str, str] | None:
    board, _ = comeet.board_from_html(page)
    if board:
        return "comeet", board
    for ats, rx, build in SIGNATURES:
        for m in rx.finditer(page):
            b = build(m)
            if b.split("/")[0].split(":")[-1].lower() not in IGNORE_BOARDS:
                return ats, b
    return None


def _candidates(base: str, page: str) -> list[str]:
    host = urlparse(base).netloc.removeprefix("www.")
    urls = []
    for rx in (CAREER_LINK, CAREER_HREF):
        for href in rx.findall(page):
            u = urljoin(base, href.strip())
            if host in urlparse(u).netloc or "comeet" in u:
                urls.append(u)
    urls += [urljoin(base, p) for p in COMMON_PATHS]
    seen, out = set(), []
    for u in urls:
        if u.rstrip("/") not in seen:
            seen.add(u.rstrip("/"))
            out.append(u)
    return out


def detect(http, target: str, max_pages: int = 12, trace: list | None = None) -> tuple[str, str] | None:
    """target: a domain ("valens.com") or a full careers URL.
    trace (optional) collects "status url" lines explaining what was tried."""
    trace = trace if trace is not None else []
    start = target if target.startswith("http") else f"https://{target}"
    queue, visited = [start], set()
    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            page = http.get_text(url)
        except Exception as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            trace.append(f"{code or type(e).__name__} {url}")
            continue
        hint = " comeet?" if "comeet" in page.lower() else ""
        trace.append(f"ok {url}{hint}")
        found = scan(page)
        if found:
            return found
        # Comeet hosted page linked from the site -> needs one more hop for the token.
        _, hosted = comeet.board_from_html(page)
        if hosted:
            board = comeet.resolve(http, hosted)
            if board:
                return "comeet", board
        # A single job page often carries the ATS link even when the list page doesn't.
        pos = POSITION_HREF.findall(page)
        if pos:
            queue.insert(0, urljoin(url, pos[0]))
        if url == start:
            queue += _candidates(url, page)
    if not visited or all(not t.startswith("ok") for t in trace):
        # the start URL itself failed: still try the common careers paths on the domain
        for p in COMMON_PATHS[:4]:
            u = urljoin(start, p)
            if u in visited:
                continue
            try:
                page = http.get_text(u)
            except Exception as e:
                code = getattr(getattr(e, "response", None), "status_code", None)
                trace.append(f"{code or type(e).__name__} {u}")
                continue
            trace.append(f"ok {u}")
            found = scan(page)
            if found:
                return found
    return None


if __name__ == "__main__":
    from .http import Http
    h = Http()
    for t in sys.argv[1:]:
        print(f"{t:30} -> {detect(h, t)}")
