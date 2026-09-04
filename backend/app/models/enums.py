import enum


class JobSource(str, enum.Enum):
    """Every value here is a source that needs zero credentials to query —
    see docs/PUBLIC_APIS_RESEARCH.md for what was investigated (including
    why Google Jobs/Upwork were removed, and why LinkedIn/Indeed aren't —
    and likely can't be — options for a personal project at all)."""

    url_import = "url_import"
    himalayas = "himalayas"
    arbeitnow = "arbeitnow"
    remotive = "remotive"
    jobicy = "jobicy"
    remotejobs_org = "remotejobs_org"
    themuse = "themuse"
    weworkremotely = "weworkremotely"
    hackernews = "hackernews"
    adzuna = "adzuna"
    usajobs = "usajobs"
    francetravail = "francetravail"
    manual = "manual"


class ApplicationStatus(str, enum.Enum):
    queued = "queued"
    passed = "passed"
    saved = "saved"
    applied = "applied"
    interviewing = "interviewing"
    offer = "offer"
    rejected = "rejected"
    withdrawn = "withdrawn"


class SwipeDecision(str, enum.Enum):
    right = "right"
    left = "left"


class GenerationSource(str, enum.Enum):
    manual = "manual"
    ai = "ai"
