import enum


class JobSource(str, enum.Enum):
    url_import = "url_import"
    google_jobs = "google_jobs"
    himalayas = "himalayas"
    upwork = "upwork"
    linkedin = "linkedin"
    indeed = "indeed"
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
