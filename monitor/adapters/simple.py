"""Adapters for ATS feeds with a plain public JSON API."""
from __future__ import annotations

from ..http import html_to_text
from ..models import Job


# --- Greenhouse: board = board token -------------------------------------------------------
def greenhouse_fetch(http, board: str, company: str) -> list[Job]:
    data = http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
                         {"content": "true"})
    return [Job(
        source=f"greenhouse:{board}", job_id=str(j["id"]), company=company,
        title=(j.get("title") or "").strip(), url=j.get("absolute_url", ""),
        location=(j.get("location") or {}).get("name", ""), posted=j.get("updated_at", ""),
        description=html_to_text(j.get("content")),
    ) for j in data.get("jobs", [])]


# --- Lever: board = slug, or "eu:<slug>" for the EU instance (jobs.eu.lever.co) -------------
def lever_fetch(http, board: str, company: str) -> list[Job]:
    eu, slug = board.startswith("eu:"), board.removeprefix("eu:")
    base = "https://api.eu.lever.co" if eu else "https://api.lever.co"
    out = []
    for p in http.get_json(f"{base}/v0/postings/{slug}", {"mode": "json"}):
        parts = [p.get("description") or ""]
        for lst in p.get("lists") or []:
            parts.append(f"<h3>{lst.get('text', '')}:</h3><ul>{lst.get('content', '')}</ul>")
        parts.append(p.get("additional") or "")
        cats = p.get("categories") or {}
        loc = cats.get("location") or ""
        if (p.get("country") or "").upper() == "IL" and "israel" not in loc.lower():
            loc = f"{loc}, Israel".strip(", ")
        out.append(Job(
            source=f"lever:{board}", job_id=p["id"], company=company,
            title=(p.get("text") or "").strip(), url=p.get("hostedUrl", ""), location=loc,
            posted=str(p.get("createdAt", "")), description=html_to_text("".join(parts)),
        ))
    return out


# --- SmartRecruiters: board = company identifier --------------------------------------------
def smartrecruiters_fetch(http, board: str, company: str) -> list[Job]:
    base = f"https://api.smartrecruiters.com/v1/companies/{board}/postings"
    jobs, offset = [], 0
    while offset < 2000:
        page = http.get_json(base, {"limit": 100, "offset": offset})
        content = page.get("content", [])
        for p in content:
            loc = p.get("location") or {}
            country = (loc.get("country") or "").lower()
            jobs.append(Job(
                source=f"smartrecruiters:{board}", job_id=str(p["id"]), company=company,
                title=(p.get("name") or "").strip(),
                url=f"https://jobs.smartrecruiters.com/{board}/{p['id']}",
                location=", ".join(x for x in [loc.get("city"), "Israel" if country == "il"
                                                else loc.get("country")] if x),
                posted=p.get("releasedDate", ""),
            ))
        offset += len(content)
        if not content or offset >= int(page.get("totalFound") or 0):
            break
    return jobs


def smartrecruiters_details(http, board: str, job: Job) -> None:
    d = http.get_json(f"https://api.smartrecruiters.com/v1/companies/{board}/postings/{job.job_id}")
    secs = ((d.get("jobAd") or {}).get("sections") or {})
    html = "".join(f"<h3>{s.get('title', '')}:</h3>{s.get('text', '')}"
                   for k, s in secs.items() if k != "companyDescription" and isinstance(s, dict))
    job.description = html_to_text(html)


# --- Amazon (incl. Annapurna Labs): board = country code, e.g. "ISR" ------------------------
def amazon_fetch(http, board: str, company: str) -> list[Job]:
    jobs = []
    for offset in range(0, 300, 100):   # newest 300 are plenty at a 30-minute cadence
        data = http.get_json("https://www.amazon.jobs/en/search.json", {
            "normalized_country_code[]": board, "result_limit": 100,
            "offset": offset, "sort": "recent"})
        batch = data.get("jobs", [])
        for j in batch:
            desc = (f"{j.get('description', '')}<h3>Basic qualifications:</h3>"
                    f"{j.get('basic_qualifications', '')}<h3>Preferred qualifications:</h3>"
                    f"{j.get('preferred_qualifications', '')}")
            jobs.append(Job(
                source=f"amazon:{board}", job_id=str(j.get("id_icims") or j.get("id")),
                company=j.get("company_name") or company, title=(j.get("title") or "").strip(),
                url="https://www.amazon.jobs" + j.get("job_path", ""),
                location=j.get("normalized_location") or j.get("location", ""),
                posted=j.get("posted_date", ""), description=html_to_text(desc),
            ))
        if len(batch) < 100:
            break
    return jobs
