from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Job:
    """One posting, normalized across all sources."""

    source: str              # "<ats>:<board>", e.g. "workday:nvidia/wd5/NVIDIAExternalCareerSite"
    job_id: str              # stable id inside the source
    company: str
    title: str
    url: str
    location: str = ""
    description: str | None = None   # plain text; None = not fetched yet
    posted: str = ""
    israel: bool | None = None       # True when the source itself was filtered to Israel
    extra: dict = field(default_factory=dict)  # adapter-private data needed for details()

    @property
    def key(self) -> str:
        return f"{self.source}#{self.job_id}"


@dataclass
class Verdict:
    status: str                      # "match" | "review" | "reject"
    reason: str = ""
    years: tuple[int, int | None] | None = None   # (min, max) required years, if stated
    grad_friendly: bool = False
    requirements: list[str] = field(default_factory=list)
