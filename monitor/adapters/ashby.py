"""Ashby's documented public job board API."""
from ..http import html_to_text
from ..models import Job


def fetch(http, board, company):
    data = http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}")
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ValueError("Ashby: missing jobs array")
    out = []
    for p in data["jobs"]:
        if p.get("isListed") is False:
            continue
        locs = [p.get("location", "")]
        locs.extend(x.get("location", "") for x in p.get("secondaryLocations", []))
        address = p.get("address") or {}
        locs.append(address.get("addressCountry", ""))
        out.append(Job(f"ashby:{board}", p["id"], company, p["title"], p["jobUrl"],
                       location=", ".join(filter(None, locs)), posted=p.get("publishedAt", ""),
                       description=p.get("descriptionPlain") or html_to_text(p.get("descriptionHtml"))))
    return out
