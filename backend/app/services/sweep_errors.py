"""Errors the automatic sweep can raise, independent of HTTP.

`run_auto_import_for_user` is called from two very different places: the
POST /jobs/search/auto-import handler, and app/scripts/run_daily_sweep.py,
which runs on a schedule with no request, no client and nobody to receive a
status code. It used to raise `HTTPException(400, ...)` for "this user has no
profile yet" — a perfectly normal condition for the scheduled sweep, reported
as a FastAPI exception in a context where nothing translates it, so the
nightly job died with a traceback instead of skipping that user.

The service raises these; the route handler translates them to 400.
"""

from __future__ import annotations


class SweepNotReady(RuntimeError):
    """The user cannot be swept yet (no profile, or nothing to search for).

    Not a failure: there is simply nothing to do for this user right now.
    Carries a message written for the end user, because the HTTP layer
    forwards it verbatim.
    """
