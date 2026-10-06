"""Workday public CXS API.

board = "<tenant>/<wdN>/<site>", e.g. "nvidia/wd5/NVIDIAExternalCareerSite".
List:   POST https://<tenant>.<wdN>.myworkdayjobs.com/wday/cxs/<tenant>/<site>/jobs  (20 per page)
Detail: GET  https://<tenant>.<wdN>.myworkdayjobs.com/wday/cxs/<tenant>/<site><externalPath>
The listing has no description, so details are fetched only for new candidate jobs.
"""
from __future__ import annotations

import re

from ..http import html_to_text
from ..models import Job

PAGE = 20
CAP = 2000
ISRAEL = re.compile(r"israel|tel[- ]aviv|haifa|yokneam|yoqneam|jerusalem|herzliya|ra'?anana|"
                    r"petah|petach|be'?er|beersheba|hod hasharon|kfar saba|netanya|rehovot|"
                    r"caesarea|kiryat|qiryat|modi'?in|ramat gan|airport city|or yehuda|tel hai|"
                    r"mevo carmel|migdal|holon|rosh ha'?ayin|matam", re.I)


def _parts(board: str):
    tenant, wd, site = board.split("/", 2)
    host = f"{tenant}.{wd}.myworkdayjobs.com"
    return host, f"https://{host}/wday/cxs/{tenant}/{site}", f"https://{host}/{site}"


def _israel_facet(facets: list, parent: str | None = None) -> dict:
    """Walk (possibly nested) facets; return {facetParameter: [ids]} for Israel locations.
    Prefers a country-level facet ("Israel") over a list of Israeli city locations."""
    country: dict[str, list[str]] = {}
    cities: dict[str, list[str]] = {}

    def walk(items, param):
        for f in items or []:
            p = f.get("facetParameter") or param
            if f.get("values"):
                walk(f["values"], p)
                continue
            desc, fid = f.get("descriptor", ""), f.get("id")
            if not fid or not p:
                continue
            if desc.strip().lower() == "israel" and "ountry" in p:
                country.setdefault(p, []).append(fid)
            elif ISRAEL.search(desc) and "ocation" in p:
                cities.setdefault(p, []).append(fid)

    walk(facets, parent)
    if country:
        return dict(list(country.items())[:1])
    if cities:
        p = max(cities, key=lambda k: len(cities[k]))
        return {p: cities[p]}
    return {}


def _page(http, api, facets, offset):
    return http.post_json(f"{api}/jobs", {"appliedFacets": facets, "limit": PAGE,
                                          "offset": offset, "searchText": ""})


def fetch(http, board: str, company: str) -> list[Job]:
    host, api, public = _parts(board)
    first = _page(http, api, {}, 0)
    facets = _israel_facet(first.get("facets", []))
    scoped = bool(facets)
    page = _page(http, api, facets, 0) if scoped else first

    postings = list(page.get("jobPostings", []))
    total = min(int(page.get("total") or 0), CAP)
    offset = len(postings)
    while offset < total:
        nxt = _page(http, api, facets, offset).get("jobPostings", [])
        if not nxt:
            break
        postings += nxt
        offset += len(nxt)

    jobs = []
    for p in postings:
        path = p.get("externalPath")
        if not path:
            continue
        jobs.append(Job(
            source=f"workday:{board}", job_id=path, company=company,
            title=(p.get("title") or "").strip(), url=public + path,
            location=p.get("locationsText", ""), posted=p.get("postedOn", ""),
            israel=True if scoped else None, extra={"api": api},
        ))
    return jobs


def details(http, board: str, job: Job) -> None:
    d = http.get_json(job.extra.get("api", _parts(board)[1]) + job.job_id).get("jobPostingInfo", {})
    job.description = html_to_text(d.get("jobDescription"))
    locs = [d.get("location", "")] + list(d.get("additionalLocations") or [])
    if any(locs):
        job.location = "; ".join(x for x in locs if x)
    if d.get("externalUrl"):
        job.url = d["externalUrl"]
