"""Apple's server-rendered search data; paginated without private API credentials."""
import json
from urllib.parse import urlencode

from .pages import unique_extend
from ..models import Job
from ..http import html_to_text

BASE = "https://jobs.apple.com"


def hydration(page):
    marker = "window.__staticRouterHydrationData = JSON.parse("
    if marker not in page:
        raise ValueError("Apple: search data missing")
    encoded, _ = json.JSONDecoder().raw_decode(page.split(marker, 1)[1])
    return json.loads(encoded)["loaderData"]


def fetch(http, board, company):
    out, seen = [], set()
    for page in range(1, 101):
        url = BASE + "/en-il/search?" + urlencode({"location": "israel-ISR", "page": page})
        data = hydration(http.get_text(url))["search"]
        batch = []
        for p in data["searchResults"]:
            locations = [", ".join(filter(None, [loc.get("name"), loc.get("countryName")]))
                         for loc in p.get("locations", [])]
            batch.append(Job(f"apple:{board}", p["id"], company, p["postingTitle"],
                             f"{BASE}/en-il/details/{p['id']}/{p['transformedPostingTitle']}",
                             location="; ".join(locations), posted=p.get("postDateInGMT", ""),
                             extra={"detail_selector": "main"}))
        unique_extend(out, batch, seen)
        if len(out) >= int(data["totalRecords"]):
            return out
        if not batch:
            raise ValueError("Apple: incomplete search results")
    raise ValueError("Apple: pagination limit reached")


def details(http, board, job):
    data = hydration(http.get_text(job.url))["jobDetails"]["jobsData"]
    if data.get("jobNumber") != job.job_id:
        raise ValueError("Apple: wrong job detail returned")
    if not data.get("minimumQualifications"):
        raise ValueError("Apple: minimum qualifications missing")
    job.description = "\n".join([
        html_to_text(data.get("jobSummary")), html_to_text(data.get("description")),
        "Minimum Qualifications:", html_to_text(data["minimumQualifications"]),
        "Preferred Qualifications:", html_to_text(data.get("preferredQualifications"))])
