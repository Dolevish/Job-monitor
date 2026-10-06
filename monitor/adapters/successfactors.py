"""Public SAP Recruiting Marketing search pages (Teva, QualityAI)."""
import re
from urllib.parse import urljoin, urlencode, urlsplit, urlunsplit, parse_qsl

from .pages import soup, text, unique_extend, description
from ..models import Job


def fetch(http, board, company):
    out, seen = [], set()
    base = board if board.startswith("https://") else "https://" + board + "/search/"
    for start in range(0, 5000, 25):
        parts = urlsplit(base)
        params = dict(parse_qsl(parts.query)) | {"startrow": start}
        url = urlunsplit(parts._replace(query=urlencode(params)))
        doc, batch = soup(http.get_text(url)), []
        for a in doc.select("a.jobTitle-link"):
            card = a.find_parent("tr") or a.parent
            target = urljoin(base, a["href"])
            jid = target.rstrip("/").rsplit("/", 1)[-1]
            batch.append(Job(f"successfactors:{board}", jid, company, text(a), target,
                             location=text(card.select_one(".jobLocation")),
                             extra={"detail_selector": ".jobdescription"}))
        unique_extend(out, batch, seen)
        label = text(doc.select_one(".paginationLabel"))
        total = re.search(r"(?:of|מתוך)\s*([\d,]+)", label, re.I)
        if total and len(out) >= int(total[1].replace(",", "")):
            return out
        if not batch:
            if re.search(r"no jobs|no results|0 (?:jobs|results)|There are currently no", text(doc), re.I):
                return out
            raise ValueError("SuccessFactors: no recognised search results")
        if not doc.select('a[href*="startrow="]'):
            return out
    raise ValueError("SuccessFactors: pagination limit reached")


details = description
