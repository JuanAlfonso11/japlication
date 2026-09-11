import enum


class JobSource(str, enum.Enum):
    """Where a `jobs` row came from: a URL or manual import, or one of the
    live search providers (keyed or not). docs/PUBLIC_APIS_RESEARCH.md covers
    what was investigated, including why Google Jobs/Upwork were removed and
    how LinkedIn came in through its public job pages."""

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
    getonbrd = "getonbrd"
    workingnomads = "workingnomads"
    remoteok = "remoteok"
    serpapi = "serpapi"
    linkedin = "linkedin"
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
