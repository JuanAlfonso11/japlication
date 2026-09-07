"""Collapses the same posting appearing many times in one search.

Measured against the live providers before writing the rules, because the
duplication turned out not to be what you'd assume. Two distinct patterns
show up, and only the second is common:

1. **The same URL indexed twice.** Cheap to catch, and real, but rare —
   about 1.7% of a "software engineer" fan-out.
2. **Geographic fan-out.** One vacancy blasted across every town in a metro
   area, each as its own ad with its own URL and its own location string. A
   single "Senior Software Engineer" at one company came back **18 times**
   from one provider — East Boston, Woonsocket, West Somerville, Hope,
   Darlington... all the same job. This is the pattern that actually floods
   the swipe queue.

Handling (2) means matching across *different* locations, which risks
merging a role genuinely offered in two cities. The description is what
separates them: a fan-out repeats one description verbatim, whereas two
real openings are written separately. So location is dropped from the key
only when the descriptions are substantial and identical.

Nothing is silently lost: when copies are merged across locations, the
surviving row's `location` says how many others there were, so a job posted
in fifteen towns still reads as covering fifteen towns.
"""

import re
import unicodedata
from typing import Iterable, Optional, TypeVar
from urllib.parse import urlsplit, urlunsplit

_PUNCTUATION_RE = re.compile(r"[^a-z0-9]+")
_REMOTE_HINTS = ("remote", "anywhere", "worldwide", "global", "distributed")

# Tracking parameters boards append to the employer's own URL. Stripping them
# is what lets two boards linking the same ATS page compare equal.
_TRACKING_PREFIXES = ("utm_", "gh_", "ref", "source", "src", "gclid", "fbclid", "mc_")

# How much description has to be present before identical text is trusted as
# evidence of "same job, different town". Two one-line stubs matching proves
# nothing; two 200-character bodies matching is not a coincidence.
_DESCRIPTION_FINGERPRINT_MIN = 120
_DESCRIPTION_FINGERPRINT_CHARS = 400


def _normalize_text(value: Optional[str]) -> str:
    """Casefold, strip accents, and reduce to alphanumeric words, so
    "Sr. Engineer — Backend" and "sr engineer backend" compare equal."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _PUNCTUATION_RE.sub(" ", without_accents.lower()).strip()


def _normalize_location(value: Optional[str]) -> str:
    """Every way of spelling "you can work from anywhere" becomes one token;
    anything else keeps its own normalized text."""
    normalized = _normalize_text(value)
    if not normalized:
        return "remote"
    if any(hint in normalized for hint in _REMOTE_HINTS):
        return "remote"
    return normalized


def _normalize_url(value: Optional[str]) -> str:
    """Drops the scheme, a leading www., tracking query parameters, the
    fragment, and any trailing slash — the parts two boards linking the same
    posting are most likely to disagree on."""
    if not value:
        return ""
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return ""
    if not parts.netloc:
        return ""

    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    kept_params = [
        pair
        for pair in parts.query.split("&")
        if pair and not pair.lower().startswith(_TRACKING_PREFIXES)
    ]
    query = "&".join(sorted(kept_params))

    path = parts.path.rstrip("/")
    return urlunsplit(("", host, path, query, "")).lstrip("/")


def _description_fingerprint(value: Optional[str]) -> str:
    """A normalized prefix of the description, or "" when there isn't enough
    text to draw a conclusion from."""
    normalized = _normalize_text(value)
    if len(normalized) < _DESCRIPTION_FINGERPRINT_MIN:
        return ""
    return normalized[:_DESCRIPTION_FINGERPRINT_CHARS]


def _completeness(result) -> tuple[int, int, int]:
    """Ranks two copies of one posting so the richer one survives. Boards
    differ a lot in what they carry — one may have the salary band, another
    only a truncated description — and keeping whichever happened to sort
    first would throw that away at random."""
    has_salary = 1 if getattr(result, "salary_min", None) is not None else 0
    has_url = 1 if getattr(result, "source_url", None) else 0
    description_length = len(getattr(result, "description", "") or "")
    return (has_salary, has_url, description_length)


def _annotate_locations(result, extra_locations: int):
    """Rewrites the surviving row's location to account for the copies that
    were merged into it, so collapsing a metro-wide fan-out never makes a
    job look narrower than it is."""
    if extra_locations <= 0:
        return result
    base = (getattr(result, "location", None) or "").strip()
    suffix = f"+{extra_locations} ubicación más" if extra_locations == 1 else f"+{extra_locations} ubicaciones más"
    merged = f"{base}  ·  {suffix}" if base else suffix
    return result.model_copy(update={"location": merged})


T = TypeVar("T")


def dedupe_external_results(results: Iterable[T]) -> list[T]:
    """Returns `results` with duplicate postings collapsed, preserving the
    input order of whichever copy is kept.

    Order is preserved rather than re-sorted because callers sort first (by
    posted date) and rely on that ordering afterwards.
    """
    index_by_key: dict[tuple, int] = {}
    kept: list[Optional[T]] = []
    # Distinct locations folded into each surviving slot, so the annotation
    # counts places rather than copies (three ads for the same town are one
    # location, not three).
    locations_by_index: list[set[str]] = []

    for result in results:
        url_key = _normalize_url(getattr(result, "source_url", None))
        company = _normalize_text(getattr(result, "company", None))
        title = _normalize_text(getattr(result, "title", None))
        location = _normalize_location(getattr(result, "location", None))
        fingerprint = _description_fingerprint(getattr(result, "description", None))

        keys: list[tuple] = []
        if url_key:
            keys.append(("url", url_key))
        # A posting with no company or no title carries too little to match
        # on safely — two different "Engineer" rows with a blank company are
        # not evidence of a duplicate — so it falls back to the URL key
        # alone, and with neither it is always kept.
        if company and title:
            keys.append(("cti", company, title, location))
            if fingerprint:
                keys.append(("ctd", company, title, fingerprint))

        existing_index = next((index_by_key[k] for k in keys if k in index_by_key), None)

        if existing_index is None:
            index = len(kept)
            kept.append(result)
            locations_by_index.append({location})
            for key in keys:
                index_by_key[key] = index
            continue

        locations_by_index[existing_index].add(location)

        # Already seen this posting: keep whichever copy carries more, in the
        # slot the first one occupied so ordering doesn't shift.
        incumbent = kept[existing_index]
        if incumbent is not None and _completeness(result) > _completeness(incumbent):
            kept[existing_index] = result
        # Point every key this copy exposes at the surviving slot, so a third
        # copy matching on either signal still resolves to the same entry.
        for key in keys:
            index_by_key.setdefault(key, existing_index)

    return [
        _annotate_locations(result, len(locations_by_index[i]) - 1)
        for i, result in enumerate(kept)
        if result is not None
    ]
