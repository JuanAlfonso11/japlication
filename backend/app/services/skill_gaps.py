"""Turns per-job match results into one actionable answer: what to learn next.

The match engine already tells you why *one* posting scored 68. What it
can't tell you is the thing that actually changes your search: across
everything you said yes to, which missing skill keeps costing you points?
That only appears once you aggregate, and nothing else in the product (or
in the auto-apply tools it competes with) does it.

The signal is deliberately drawn from jobs the user showed interest in
rather than from everything that flowed past. A skill that's missing from
postings you swiped away is noise; one missing from the roles you actually
want is a gap worth closing.
"""

from collections import Counter
from typing import Iterable, Optional

# A skill seen once is an anecdote. Two is the floor at which "this keeps
# coming up" is even arguable, and below it the list fills with one-off
# tools nobody should reorganize their learning around.
_MIN_OCCURRENCES = 2


def _normalize(skill: str) -> str:
    return " ".join(skill.strip().lower().split())


def aggregate_skill_gaps(
    missing_skills_per_job: Iterable[Iterable[str]],
    limit: int = 8,
) -> tuple[list[dict], int]:
    """Counts how often each skill is missing across the given jobs.

    Takes one iterable of missing-skill names per job. Returns
    `(gaps, jobs_considered)` where each gap carries the skill's display
    label, how many of those jobs wanted it, and what share that is — the
    percentage is what makes it actionable ("in 60% of what you saved"
    lands differently from "12 times").
    """
    jobs = [list(skills) for skills in missing_skills_per_job]
    total_jobs = len(jobs)
    if total_jobs == 0:
        return [], 0

    counts: Counter[str] = Counter()
    # Keeps the nicest-looking original spelling for each normalized key, so
    # the UI shows "PostgreSQL" rather than whatever casing won the race.
    labels: dict[str, str] = {}

    for skills in jobs:
        # A skill counts once per job even if the posting lists it twice,
        # otherwise a single verbose job description could outvote a real
        # pattern across many postings.
        seen_in_job = set()
        for raw in skills:
            if not raw or not raw.strip():
                continue
            key = _normalize(raw)
            if key in seen_in_job:
                continue
            seen_in_job.add(key)
            counts[key] += 1
            existing = labels.get(key)
            # Prefer the spelling with capitals — job posts write real
            # product names properly and lowercase them by accident.
            if existing is None or (raw.strip() != raw.strip().lower() and existing == existing.lower()):
                labels[key] = raw.strip()

    gaps = [
        {
            "skill": labels[key],
            "job_count": count,
            "percentage": round(count / total_jobs * 100),
        }
        for key, count in counts.most_common()
        if count >= _MIN_OCCURRENCES
    ]

    return gaps[:limit], total_jobs


def summarize(gaps: list[dict], total_jobs: int) -> Optional[str]:
    """One plain sentence for the top of the card, or None when there isn't
    enough data to say anything honest."""
    if not gaps or total_jobs == 0:
        return None
    top = gaps[0]
    return (
        f"{top['skill']} aparece en {top['percentage']}% de las vacantes que te interesaron "
        f"y no está en tu perfil."
    )
