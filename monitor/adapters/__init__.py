"""Registry: ats name -> (fetch, details). details may be None when fetch already
returns full descriptions."""
from __future__ import annotations

from . import comeet, simple, workday

ADAPTERS = {
    "workday": (workday.fetch, workday.details),
    "greenhouse": (simple.greenhouse_fetch, None),
    "lever": (simple.lever_fetch, None),
    "smartrecruiters": (simple.smartrecruiters_fetch, simple.smartrecruiters_details),
    "amazon": (simple.amazon_fetch, None),
    "comeet": (comeet.fetch, None),
}

# Known ATS we can detect but have no adapter for yet (phase 2).
PLANNED = {"oracle_hcm", "eightfold", "successfactors", "apple", "google", "ashby",
           "workable", "bamboohr", "teamtailor", "recruitee", "breezy", "phenom"}


def source_key(ats: str, board: str) -> str:
    """Stable id of a feed. Comeet keys on the company uid only, so a rotated token
    doesn't look like a brand-new source."""
    if ats == "comeet":
        return f"comeet:{board.split('|', 1)[0]}"
    return f"{ats}:{board}"
