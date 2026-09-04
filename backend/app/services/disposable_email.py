"""Blocks registration from disposable/temporary email domains, using a
vendored snapshot of https://github.com/eramitgupta/disposable-email
(app/data/disposable_email_domains.json — a flat JSON array of ~125k
domains, MIT licensed, updated daily upstream). Vendored rather than
fetched at request time so a signup never depends on an external service
being up; refresh the snapshot periodically by re-downloading that file.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "disposable_email_domains.json"


@lru_cache
def _domains() -> frozenset[str]:
    with open(_DATA_PATH, encoding="utf-8") as f:
        return frozenset(d.strip().lower() for d in json.load(f) if d.strip())


def is_disposable_email(email: str) -> bool:
    domain = email.rsplit("@", 1)[-1].strip().lower()
    return domain in _domains()
