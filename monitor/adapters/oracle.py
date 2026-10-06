"""Oracle Fusion's public Candidate Experience API (no login required)."""
from __future__ import annotations

from ..http import html_to_text
from ..models import Job


def endpoint(board):
    host, site = board.split("/", 1)
    if "." not in host:
        host += ".fa.us2.oraclecloud.com"
    return f"https://{host}", site


def fetch(http, board, company):
    base, site = endpoint(board)
    out, seen = [], set()
    for offset in range(0, 5000, 100):
        data = http.get_json(base + "/hcmRestApi/resources/latest/recruitingCEJobRequisitions", {
            "onlyData": "true", "expand": "requisitionList",
            "finder": f"findReqs;siteNumber={site},location=Israel,limit=100,offset={offset}"})
        groups = data.get("items")
        if not groups or "requisitionList" not in groups[0]:
            raise ValueError("Oracle: missing requisitionList")
        page = groups[0]
        total = int(page["TotalJobsCount"])
        batch = page["requisitionList"]
        for item in batch:
            jid = str(item["Id"])
            if jid in seen:
                raise ValueError("Oracle: repeated job/page")
            seen.add(jid)
            out.append(Job(f"oracle_hcm:{board}", jid, company, item["Title"],
                           f"{base}/hcmUI/CandidateExperience/en/sites/{site}/job/{jid}",
                           location=item.get("PrimaryLocation", ""),
                           posted=item.get("PostedDate", "")))
        if len(out) >= total:
            return out
        if not batch:
            raise ValueError("Oracle: incomplete pagination")
    raise ValueError("Oracle: pagination limit reached")


def details(http, board, job):
    base, _ = endpoint(board)
    data = http.get_json(base + "/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails", {
        "onlyData": "true", "finder": f"ById;Id={job.job_id}"})
    items = data.get("items", [])
    if not items or str(items[0].get("Id")) != job.job_id:
        raise ValueError("Oracle: missing job details")
    item = items[0]
    job.description = html_to_text("\n".join(item.get(k) or "" for k in (
        "ExternalDescriptionStr", "ExternalQualificationsStr", "ExternalResponsibilitiesStr")))
    if not job.description:
        raise ValueError("Oracle: empty job description")
