"""Google Careers' public server-rendered listings and next-page links."""
import re
from urllib.parse import urljoin

from .pages import soup, text, description, unique_extend, same_host_link
from ..models import Job

BASE = "https://www.google.com/about/careers/applications/"


def fetch(http, board, company):
    url = BASE + "jobs/results/?location=Israel"
    out, seen, pages = [], set(), set()
    while url and len(pages) < 100:
        if url in pages:
            raise ValueError("Google: repeated next-page URL")
        pages.add(url)
        doc, batch = soup(http.get_text(url)), []
        for a in doc.select('a[href]'):
            match = re.search(r"jobs/results/(\d+)-", a["href"])
            if not match:
                continue
            card = a.find_parent("li")
            if card is None or card.select_one("h3") is None:
                raise ValueError("Google: job card schema changed")
            batch.append(Job(f"google:{board}", match[1], company, text(card.select_one("h3")),
                             urljoin(BASE, a["href"]),
                             location="; ".join(dict.fromkeys(text(e) for e in card.select(".r0wTof"))),
                             extra={"detail_selector": "main, [role=main]"}))
        unique_extend(out, batch, seen)
        if not batch and not re.search(r"no (?:matching |search )?(?:jobs|results)", text(doc), re.I):
            raise ValueError("Google: missing results")
        link = doc.select_one('a[aria-label="Go to next page"]')
        url = same_host_link(url, link["href"]) if link else None
    if url:
        raise ValueError("Google: pagination limit reached")
    return out


details = description
