"""Eightfold PCSX public careers API (Qualcomm and Microsoft).

board = "<careers-host>|<domain>", e.g. "careers.qualcomm.com|qualcomm.com".
The endpoints and pagination mirror the public site's PCSX client; no login is needed.
"""
from __future__ import annotations

from urllib.parse import urljoin

from ..http import html_to_text
from ..models import Job

CAP = 2000


def _parts(board: str) -> tuple[str, str]:
    host, domain = board.split("|", 1)
    if not host or "/" in host or not domain or "/" in domain:
        raise ValueError("Eightfold board must be <careers-host>|<domain>")
    return f"https://{host}", domain


def _data(body: dict) -> dict:
    data = body.get("data")
    error = body.get("error")
    has_error = any(error.values()) if isinstance(error, dict) else bool(error)
    if has_error or body.get("status", 200) != 200 or not isinstance(data, dict):
        raise ValueError("Invalid Eightfold response")
    return data


def fetch(http, board: str, company: str) -> list[Job]:
    base, domain = _parts(board)
    jobs, seen, start = [], set(), 0
    while start < CAP:
        data = _data(http.get_json(base + "/api/pcsx/search", {
            "domain": domain, "location": "Israel", "query": "", "start": start,
        }))
        if not isinstance(data.get("positions"), list) or "count" not in data:
            raise ValueError("Eightfold search missing positions/count")
        total, batch = int(data["count"]), data["positions"]
        if total > CAP:
            raise ValueError(f"Eightfold Israel feed exceeds {CAP} jobs; refine the query")
        if not batch:
            if start < total:
                raise ValueError("Eightfold pagination stopped before all jobs were fetched")
            break
        added = 0
        for p in batch:
            if not p.get("id") or not p.get("name"):
                raise ValueError("Eightfold position missing id/name")
            jid = str(p["id"])
            if jid in seen:
                continue
            seen.add(jid)
            added += 1
            jobs.append(Job(
                source=f"eightfold:{board}", job_id=jid, company=company,
                title=p["name"].strip(),
                url=urljoin(base, p.get("publicUrl") or p.get("positionUrl") or f"/careers/job/{jid}"),
                location="; ".join(p.get("locations") or [p.get("location") or ""]),
                posted=str(p.get("postedTs") or ""),
            ))
        if not added:
            raise ValueError("Eightfold returned a repeated page")
        start += len(batch)
        if start >= total:
            break
    return jobs


def details(http, board: str, job: Job) -> None:
    base, domain = _parts(board)
    data = _data(http.get_json(base + "/api/pcsx/position_details", {
        "domain": domain, "position_id": job.job_id, "hl": "en",
    }))
    if "jobDescription" not in data or str(data.get("id")) != job.job_id:
        raise ValueError("Eightfold detail response missing description or wrong position")
    job.description = html_to_text(data["jobDescription"])
    if data.get("locations"):
        job.location = "; ".join(data["locations"])
    if data.get("publicUrl"):
        job.url = urljoin(base, data["publicUrl"])
