"""Registry: ats name -> (fetch, details). details may be None when fetch already
returns full descriptions."""
from __future__ import annotations

from . import (comeet, eightfold, simple, workday, apple, ashby, company_sites,
               google, hibob, israeli, jobify, jobnet, oracle, successfactors, wordpress, experis, taleo)

ADAPTERS = {
    "taleo": (taleo.fetch, taleo.details),
    "apple": (apple.fetch, apple.details),
    "google": (google.fetch, google.details),
    "ashby": (ashby.fetch, None),
    "oracle_hcm": (oracle.fetch, oracle.details),
    "successfactors": (successfactors.fetch, successfactors.details),
    "site": (company_sites.fetch, company_sites.details),
    "elbit": (israeli.elbit_fetch, None),
    "ness": (israeli.ness_fetch, None),
    "jobify": (jobify.fetch, jobify.details),
    "jobnet": (jobnet.fetch, None),
    "hibob": (hibob.fetch, None),
    "wordpress": (wordpress.fetch, wordpress.details),
    "experis": (experis.fetch, company_sites.details),
    "workday": (workday.fetch, workday.details),
    "greenhouse": (simple.greenhouse_fetch, None),
    "lever": (simple.lever_fetch, None),
    "smartrecruiters": (simple.smartrecruiters_fetch, simple.smartrecruiters_details),
    "amazon": (simple.amazon_fetch, None),
    "comeet": (comeet.fetch, None),
    "eightfold": (eightfold.fetch, eightfold.details),
}

# Known ATS we can detect but have no adapter for yet (phase 2).
PLANNED = {"workable", "bamboohr", "teamtailor", "recruitee", "breezy", "phenom"}


def source_key(ats: str, board: str) -> str:
    """Stable id of a feed. Comeet keys on the company uid only, so a rotated token
    doesn't look like a brand-new source."""
    if ats == "comeet":
        return f"comeet:{board.split('|', 1)[0]}"
    return f"{ats}:{board}"
