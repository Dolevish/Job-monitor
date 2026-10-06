"""Decides whether a posting fits: title, Israel location, and required years of experience.

No LLM: years are pulled from the description with English + Hebrew patterns, ignoring
lines that are marked optional ("advantage", "preferred", "יתרון") or sit under an
optional heading ("Nice to have:", "Preferred Qualifications").
"""
from __future__ import annotations

import re

from .models import Job, Verdict

_NUM = r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)"
_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten".split())}

EN_YEARS = re.compile(
    rf"\b{_NUM}\s*\+?\s*(?:plus\s*)?(?:(?:-|–|—|to)\s*{_NUM}\s*\+?\s*)?(?:years?|yrs?)\b", re.I)
HE_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:(?:-|–|—|עד)\s*(\d{1,2})\s*\+?\s*)?שנ(?:ות|ים|ה|ת)\b")
HE_ONE_YEAR = re.compile(r"שנת\s+(?:ניסיון|נסיון|עבודה)|שנה\s+(?:אחת\s+)?(?:של\s+)?(?:ניסיון|נסיון)")
EXP_WORD = re.compile(r"experience|\bexp\b|ניסיון|נסיון", re.I)
OPTIONAL_LINE = re.compile(r"advantage|\bplus\b|preferred|nice to have|bonus|desirabl|יתרון", re.I)
OPTIONAL_HEADING = re.compile(
    r"preferred|nice to have|bonus|advantage|desired|יתרון|יתרונות", re.I)
COMPANY_LINE = re.compile(r"\bcompany\b|\bfounded\b|\bfor over\b|\bindustry for\b|החברה", re.I)
HEADING_WORDS = re.compile(
    r"requirement|qualification|responsibilit|about|what you|you have|you bring|you'll|"
    r"looking for|nice to have|preferred|advantage|benefit|the role|the position|"
    r"דרישות|יתרונות|תיאור|תחומי אחריות|מה אנחנו|כישורים", re.I)
REQ_HEADING = re.compile(
    r"requirement|qualification|what you(?:'ll)? (?:need|bring)|you have|you bring|"
    r"looking for|about you|must have|דרישות|כישורים|מה אנחנו מחפשים|מה צריך", re.I)
GRAD = re.compile(
    r"no (?:prior |previous )?experience|without experience|new grad|new college grad|"
    r"recent(?:ly)? grad|fresh grad|graduates? (?:are )?welcome|entry[- ]level|early career|"
    r"\b0\s*(?:-|–|to)\s*[1-3]\s*years|\b0\+?\s*years|graduate program|"
    r"ללא ניסיון|ללא נסיון|בוגר(?:ים|ות|/ת)?\s+טרי|בוגרי תואר|ג'וניור", re.I)
BULLET = re.compile(r"^\s*(?:[•\-\*·▪●◦]|\d+[.)])\s*")
AMBIGUOUS_LOC = re.compile(r"^\s*$|\d+\s+locations?", re.I)
ADVANCED_DEGREE = re.compile(r"\bph\.?\s*d\.?\b|\bdoctor(?:ate|al)\b|\bm\.?\s*sc\.?\b|"
                             r"\bm\.?\s*s\.?(?=\s+(?:degree|in)\b|\s*[/,])|"
                             r"\bmaster(?:'s|’s|s)\b|\bmaster\s+(?:degree|of)\b|"
                             r"דוקטורט|תואר\s+(?:שני|שלישי)", re.I)
BACHELOR = re.compile(r"\bbachelor(?:'s|’s|s)?\b|\bb\.?\s*sc\.?\b|\bb\.?\s*s\.?\b|"
                      r"\bb\.?\s*eng\.?\b|תואר\s+ראשון", re.I)
MANDATORY = re.compile(r"\brequired\b|\bmust\b|\bminimum\b|\bmandatory\b|חובה|נדרש", re.I)


def _bachelor_alternative(line: str) -> bool:
    degree, bachelor = ADVANCED_DEGREE.search(line), BACHELOR.search(line)
    if not degree or not bachelor:
        return False
    a, b = sorted((degree, bachelor), key=lambda m: m.start())
    between = line[a.end():b.start()]
    return bool(re.search(r"\bor\b|או", between, re.I) or re.fullmatch(r"[\s.]*/[\s.]*", between))


def required_advanced_degree(text: str) -> str | None:
    """Reject mandatory postgraduate study, while allowing B.Sc. alternatives/preferences."""
    in_req, optional = False, False
    for raw in text.splitlines():
        line = raw.strip()
        degree = ADVANCED_DEGREE.search(line)
        if not degree and _is_heading(line):
            in_req = bool(REQ_HEADING.search(line))
            optional = bool(OPTIONAL_HEADING.search(line))
            continue
        if not degree or optional or OPTIONAL_LINE.search(line):
            continue
        if _bachelor_alternative(line):
            continue
        bullet_degree = BULLET.match(line) and ADVANCED_DEGREE.match(BULLET.sub("", line))
        if in_req or MANDATORY.search(line) or bullet_degree:
            return degree.group().strip()
    return None


def _n(tok: str | None) -> int | None:
    if tok is None:
        return None
    tok = tok.lower()
    return int(tok) if tok.isdigit() else _WORDS.get(tok)


def _is_heading(line: str) -> bool:
    if BULLET.match(line) or len(line) > 80:
        return False
    return line.rstrip().endswith(":") or (len(line) < 60 and bool(HEADING_WORDS.search(line)))


def _year_spans(line: str) -> list[tuple[int, int | None]]:
    spans: list[tuple[int, int | None]] = []
    for m in EN_YEARS.finditer(line):
        lo, hi = _n(m.group(1)), _n(m.group(2))
        if lo is not None and lo <= 20:
            spans.append((lo, hi))
    for m in HE_YEARS.finditer(line):
        spans.append((int(m.group(1)), int(m.group(2)) if m.group(2) else None))
    if HE_ONE_YEAR.search(line):
        spans.append((1, None))
    return spans


def required_years(text: str) -> tuple[int, int | None] | None:
    """Largest mandatory lower bound of years of experience, with its upper bound if a range."""
    best: tuple[int, int | None] | None = None
    optional_section, in_requirements = False, False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _is_heading(line):
            optional_section = bool(OPTIONAL_HEADING.search(line))
            in_requirements = bool(REQ_HEADING.search(line))
            continue
        if optional_section or not (EXP_WORD.search(line) or in_requirements):
            continue
        if OPTIONAL_LINE.search(line) or COMPANY_LINE.search(line):
            continue
        for span in _year_spans(line):
            if best is None or span[0] > best[0]:
                best = span
    return best


def requirements(text: str, limit: int = 6) -> list[str]:
    """First few lines of the requirements section (fallback: lines that mention years/degree)."""
    out: list[str] = []
    in_req = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _is_heading(line):
            in_req = bool(REQ_HEADING.search(line)) and not OPTIONAL_HEADING.search(line)
            continue
        if in_req:
            out.append(_clip(BULLET.sub("", line)))
            if len(out) >= limit:
                break
    if not out:
        pat = re.compile(r"years?|degree|b\.?sc|c\+\+|\bc\b|linux|ניסיון|תואר", re.I)
        out = [_clip(BULLET.sub("", ln.strip())) for ln in text.splitlines() if pat.search(ln)][:limit]
    return out


def _clip(s: str, n: int = 140) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


class Filters:
    def __init__(self, cfg: dict):
        def rx(items):
            return re.compile("|".join(f"(?:{p})" for p in items), re.I) if items else None

        self.max_years = int(cfg.get("max_years", 1))
        self.core = rx(cfg.get("title_core", []))
        self.general = rx(cfg.get("title_general", []))
        self.junior = rx(cfg.get("title_junior", []))
        self.exclude = rx(cfg.get("title_exclude", []))
        self.adjacent = rx(cfg.get("title_adjacent", []))
        self.bachelors_compatible = bool(cfg.get("bachelors_compatible", True))
        self.israel = rx(cfg.get("locations", ["israel"]))

    # --- cheap checks, before fetching the description ---
    def title_ok(self, title: str) -> bool:
        if self.exclude and self.exclude.search(title):
            return False
        if (self.bachelors_compatible and ADVANCED_DEGREE.search(title)
                and not OPTIONAL_LINE.search(title) and not _bachelor_alternative(title)):
            return False
        if self.core and self.core.search(title):
            return True
        return bool(self.general and self.junior and self.general.search(title)
                    and self.junior.search(title))

    def location_ok(self, job: Job) -> bool | None:
        """True / False, or None when the listing doesn't say (decide after details)."""
        if job.israel:
            return True
        if self.israel.search(job.location or ""):
            return True
        if AMBIGUOUS_LOC.search(job.location or ""):
            return None
        return False

    def is_candidate(self, job: Job) -> bool:
        return self.title_ok(job.title) and self.location_ok(job) is not False

    # --- full decision, after the description is available ---
    def classify(self, job: Job) -> Verdict:
        if not self.title_ok(job.title):
            return Verdict("reject", "title")
        text = job.description or ""
        loc = self.location_ok(job)
        if loc is None:
            loc = bool(self.israel.search(text[:600]))
        if not loc:
            return Verdict("reject", "location")

        degree = required_advanced_degree(text) if self.bachelors_compatible else None
        if degree:
            return Verdict("reject", f"required degree: {degree}")

        grad = bool(GRAD.search(job.title) or GRAD.search(text)
                    or (self.junior and self.junior.search(job.title)))
        years = required_years(text)
        reqs = requirements(text)
        adjacent = bool(self.adjacent and self.adjacent.search(job.title)
                        and not (self.core and self.core.search(job.title)))
        if years is None:
            return Verdict("match" if grad and not adjacent else "review",
                           "adjacent field" if adjacent else "no years stated", None, grad, reqs)
        lo, hi = years
        if lo > self.max_years:
            return Verdict("reject", f"{lo}+ years", years, grad, reqs)
        if hi is not None and hi > self.max_years and lo >= 1 and not grad:
            return Verdict("reject", f"{lo}-{hi} years", years, grad, reqs)
        return Verdict("review" if adjacent else "match", "adjacent field" if adjacent else "years ok",
                       years, grad, reqs)
