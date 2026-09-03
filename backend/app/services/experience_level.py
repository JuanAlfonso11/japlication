"""A shared experience-level taxonomy used to filter job search results
uniformly across every provider in `GET /jobs/search/aggregate`, regardless
of whether that provider exposes a native "seniority" concept.

Taxonomy: "internship" | "entry" | "mid" | "senior" | "lead"

- Himalayas and The Muse accept a native filter parameter for this — map our
  taxonomy value to *their* vocabulary with `to_himalayas()` / `to_muse()`.
- Jobicy returns a native `jobLevel` string on each result — normalize it
  with `normalize_native()`.
- Arbeitnow, Remotive, and RemoteJobs.org expose neither, so `infer()` scans
  the job's title/description with the same kind of keyword heuristic
  job_importer.py already uses for `seniority`, giving every provider's
  results a best-effort, filterable level.
"""

from __future__ import annotations

from typing import Optional

LEVELS = ("internship", "entry", "mid", "senior", "lead")

# Ordered most-specific-first so "senior director" matches "lead" via
# "director" before a looser rule could misfire.
_KEYWORD_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("internship", ("intern", "internship", "pasantía", "pasantia", "becario", "trainee", "traineeship")),
    ("lead", ("lead", "principal", "staff", "director", "head of", "vp", "vice president", "chief", "manager", "management")),
    ("senior", ("senior", "sr.", "sr ")),
    ("entry", ("entry-level", "entry level", "junior", "jr.", "jr ", "graduate", "new grad")),
    ("mid", ("mid-level", "mid level", "midweight", "intermediate")),
]

# The Muse's own `levels[].name` / `level` filter values.
_MUSE_VALUES = {
    "internship": "Internship",
    "entry": "Entry Level",
    "mid": "Mid Level",
    "senior": "Senior Level",
    "lead": "Management",
}

# Himalayas' own `seniority` filter values (comma-joinable).
_HIMALAYAS_VALUES = {
    "internship": "Entry-level",  # Himalayas has no dedicated internship bucket
    "entry": "Entry-level",
    "mid": "Mid-level",
    "senior": "Senior",
    "lead": "Manager,Director,Executive",
}

# Loose keyword match for providers that DO return a level-ish string
# (e.g. Jobicy's `jobLevel`) but not from a fixed enum we can trust blindly.
_NATIVE_KEYWORD_RULES = _KEYWORD_RULES


def infer(*texts: Optional[str]) -> Optional[str]:
    """Best-effort level from free text (title + description, etc.). Returns
    None when nothing matches — callers should treat that as "unknown", not
    as any specific level, so it isn't wrongly excluded by a filter."""
    haystack = " ".join(t for t in texts if t).lower()
    if not haystack:
        return None
    for level, keywords in _KEYWORD_RULES:
        if any(kw in haystack for kw in keywords):
            return level
    return None


def normalize_native(raw: Optional[str]) -> Optional[str]:
    """Normalize a provider-supplied level string (e.g. Jobicy's `jobLevel`,
    or The Muse's `levels[0].name`) to our taxonomy via the same keyword
    rules used for inference — providers rarely use our exact vocabulary."""
    if not raw:
        return None
    return infer(raw)


def to_muse(level: str) -> Optional[str]:
    return _MUSE_VALUES.get(level)


def to_himalayas(level: str) -> Optional[str]:
    return _HIMALAYAS_VALUES.get(level)


def matches(level: Optional[str], wanted: Optional[str]) -> bool:
    """Filter predicate: keep results with an unknown level (None) rather
    than silently dropping them — better to over-show than to hide a real
    match just because we couldn't classify it."""
    if not wanted:
        return True
    if level is None:
        return True
    return level == wanted
