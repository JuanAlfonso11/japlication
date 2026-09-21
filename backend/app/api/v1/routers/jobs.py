import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.models.application import Application
from app.models.career_profile import CareerProfile
from app.models.device_token import DeviceToken
from app.models.enums import ApplicationStatus, JobSource
from app.models.job import Job
from app.models.job_match import JobMatch
from app.models.user import User
from app.schemas.job import Job as JobSchema
from app.schemas.job import (
    AggregateSearchResponse,
    AggregateSourceStatus,
    AutoImportResponse,
    ExternalJobImportRequest,
    ExternalJobResult,
    ExternalJobsSearchResponse,
    JobCreate,
    JobImportRequest,
    JobListResponse,
)
from app.schemas.job_match import MatchResult
# The 15 connector modules are no longer imported here: the router does not
# name any provider any more, it looks them up in the registry.
from app.services import api_budget, push_notifications
from app.services.apply_target import detect_ats
from app.services.job_dedupe import dedupe_external_results
from app.services.job_importer import (
    JobImportError,
    _extract_remote_type,
    import_job_from_url,
)
from app.services.match_engine import compute_and_persist_match
from app.services.external_jobs import (
    PROVIDER_NAMES,
    PROVIDER_NAMES_PATTERN,
    SearchParams,
    get_provider,
)
from app.services.external_jobs import result_cache
from app.services.external_jobs.http import ProviderUnavailable
from app.services.external_jobs.registry import NO_AUTH_PROVIDERS, normalize_results
from app.services.sweep_errors import SweepNotReady

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])

# Every JobSource enum value that comes from a live search provider (as
# opposed to url_import/manual) — see docs/PUBLIC_APIS_RESEARCH.md for what
# was investigated, why Google Jobs/Upwork/Indeed aren't part of this list,
# and how LinkedIn got in through its public job pages.
#
# Derived from the provider registry rather than written out again, so these
# lists cannot drift from the providers that actually exist. The keyed ones
# (adzuna, usajobs, serpapi) degrade gracefully when their .env keys are
# missing: their search raises a clear *Error, which the single-provider
# endpoint turns into a 502 and the aggregate turns into a per-source error
# message — never a hard failure for the others.
_NO_AUTH_PROVIDERS = NO_AUTH_PROVIDERS
_KEYED_PROVIDERS = frozenset(PROVIDER_NAMES) - NO_AUTH_PROVIDERS
_SEARCH_PROVIDERS = frozenset(PROVIDER_NAMES)

# Adzuna and SerpApi both have a monthly call quota (1,000/month and
# 250/month respectively — docs/PUBLIC_APIS_RESEARCH.md #9 and #12); an
# unattended 2-hour sweep alone would be 12 calls/day (~360/month) to each,
# already over SerpApi's quota before counting a single manual Discover
# search. app.services.api_budget caps every quota-limited provider at
# DAILY_CALL_BUDGET (8) calls/day — 240/month, safely under both quotas —
# enforced once, inside _run_search_provider below, so it applies
# uniformly everywhere a provider gets called: the scheduled sweep, pull-
# to-refresh, and Discover's explicit search all share the same daily
# budget rather than each needing their own carve-out.

async def _ensure_match(job: Job, user_id: UUID, db: AsyncSession) -> None:
    """Computes and persists a JobMatch for a freshly-added job, if the
    user has a saved career profile to score it against. Without this,
    GET /matches (an INNER JOIN against job_matches) would silently never
    surface a job added via URL import, manual creation, or "add to
    queue" from Discover — nothing else computes a match for it, unlike
    the automatic sweep (run_auto_import_for_user), which always has.
    A no-op (not an error) if there's no profile yet — same
    graceful-degradation as everywhere else a career profile is optional."""
    existing = await db.execute(
        select(JobMatch.id).where(JobMatch.user_id == user_id, JobMatch.job_id == job.id)
    )
    if existing.scalar_one_or_none() is not None:
        return
    profile = (
        await db.execute(select(CareerProfile).where(CareerProfile.user_id == user_id))
    ).scalar_one_or_none()
    if profile is None:
        return
    await compute_and_persist_match(profile, job, user_id, db)


async def _attach_match(job: Job, user_id: UUID, db: AsyncSession) -> JobSchema:
    schema = JobSchema.model_validate(job)
    result = await db.execute(
        select(JobMatch).where(JobMatch.user_id == user_id, JobMatch.job_id == job.id)
    )
    match = result.scalar_one_or_none()
    if match is not None:
        schema.match = MatchResult.model_validate(match)
    return schema


@router.post("/jobs/import", response_model=JobSchema, status_code=status.HTTP_201_CREATED)
# Sin limite, este endpoint era el unico del router que no lo tenia, y es el
# mas caro de todos: ver el to_thread de abajo.
@limiter.limit("10/minute")
async def import_job(
    request: Request,
    payload: JobImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobSchema:
    existing = await db.execute(select(Job).where(Job.source_url == payload.url))
    existing_job = existing.scalar_one_or_none()
    if existing_job is not None:
        await _ensure_match(existing_job, current_user.id, db)
        return await _attach_match(existing_job, current_user.id, db)

    # The importer raises its own JobImportError now, like the other 15 job
    # services; translating it to a status code is the router's job.
    try:
        parsed = await import_job_from_url(payload.url)
    except JobImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job = Job(
        imported_by=current_user.id,
        source=JobSource.url_import,
        source_url=parsed.get("source_url"),
        title=parsed["title"],
        company=parsed["company"],
        location=parsed.get("location"),
        remote_type=parsed.get("remote_type"),
        employment_type=parsed.get("employment_type"),
        seniority=parsed.get("seniority"),
        description=parsed["description"],
        requirements=parsed.get("requirements") or [],
        responsibilities=parsed.get("responsibilities") or [],
        skills_required=parsed.get("skills_required") or [],
        salary_min=parsed.get("salary_min"),
        salary_max=parsed.get("salary_max"),
        salary_currency=parsed.get("salary_currency"),
        posted_at=parsed.get("posted_at"),
        deadline=parsed.get("deadline"),
        raw_html=parsed.get("raw_html"),
    )
    db.add(job)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        # Race: another request imported the same URL concurrently.
        existing = await db.execute(select(Job).where(Job.source_url == payload.url))
        existing_job = existing.scalar_one_or_none()
        if existing_job is not None:
            await _ensure_match(existing_job, current_user.id, db)
            return await _attach_match(existing_job, current_user.id, db)
        raise HTTPException(status_code=422, detail="could not parse job posting")
    await db.refresh(job)
    await _ensure_match(job, current_user.id, db)
    return await _attach_match(job, current_user.id, db)


@router.post("/jobs", response_model=JobSchema, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobSchema:
    if payload.source_url:
        existing = await db.execute(select(Job).where(Job.source_url == payload.source_url))
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="A job with this source_url already exists.")

    job = Job(
        imported_by=current_user.id,
        source=JobSource.manual,
        source_url=payload.source_url,
        title=payload.title,
        company=payload.company,
        location=payload.location,
        remote_type=payload.remote_type,
        employment_type=payload.employment_type,
        seniority=payload.seniority,
        description=payload.description,
        requirements=payload.requirements,
        responsibilities=payload.responsibilities,
        skills_required=[s.model_dump() for s in payload.skills_required],
        salary_min=payload.salary_min,
        salary_max=payload.salary_max,
        salary_currency=payload.salary_currency,
        posted_at=payload.posted_at,
        deadline=payload.deadline,
        requires_cover_letter=payload.requires_cover_letter,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await _ensure_match(job, current_user.id, db)
    return await _attach_match(job, current_user.id, db)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    query: Optional[str] = Query(None),
    status_filter: Optional[ApplicationStatus] = Query(None, alias="status"),
    min_score: Optional[float] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobListResponse:
    base = select(Job)
    count_base = select(func.count(Job.id.distinct()))

    if status_filter is not None:
        base = base.join(Application, (Application.job_id == Job.id) & (Application.user_id == current_user.id))
        base = base.where(Application.status == status_filter)
        count_base = count_base.join(
            Application, (Application.job_id == Job.id) & (Application.user_id == current_user.id)
        ).where(Application.status == status_filter)

    if min_score is not None:
        base = base.join(JobMatch, (JobMatch.job_id == Job.id) & (JobMatch.user_id == current_user.id))
        base = base.where(JobMatch.overall_score >= min_score)
        count_base = count_base.join(
            JobMatch, (JobMatch.job_id == Job.id) & (JobMatch.user_id == current_user.id)
        ).where(JobMatch.overall_score >= min_score)

    if query:
        # `jobs.search_vector` is a stored tsvector with a GIN index
        # (idx_jobs_search) built over title + company + description. The old
        # filter was three ILIKE '%…%' patterns, which no index can serve:
        # every search was a sequential scan of the whole table, description
        # column included, and the table grows ~20 rows every 2 hours.
        #
        # ILIKE stays as a fallback OR-ed in, because full-text search is not
        # a superset of substring matching: it works on whole lemmas, so
        # "Postgre" would no longer find "PostgreSQL" and a partial company
        # name would stop matching. The indexed branch answers the common
        # case cheaply; the scan only has to consider what it did not match.
        like = f"%{query}%"
        # Raw SQL for this one term: `search_vector` is a generated column
        # that the ORM model deliberately does not map (nothing ever writes
        # it), so there is no attribute to build the operator from. Bound
        # parameter, never string interpolation.
        text_match = text(
            "jobs.search_vector @@ websearch_to_tsquery('spanish', :fts_query)"
        ).bindparams(fts_query=query)
        predicate = or_(
            text_match,
            Job.title.ilike(like),
            Job.company.ilike(like),
            Job.description.ilike(like),
        )
        base = base.where(predicate)
        count_base = count_base.where(predicate)

    total = (await db.execute(count_base)).scalar_one()

    base = base.order_by(Job.created_at.desc()).limit(limit).offset(offset)
    jobs = (await db.execute(base)).scalars().all()

    matches_by_job_id: dict[UUID, JobMatch] = {}
    if jobs:
        match_rows = (
            await db.execute(
                select(JobMatch).where(
                    JobMatch.user_id == current_user.id,
                    JobMatch.job_id.in_([job.id for job in jobs]),
                )
            )
        ).scalars().all()
        matches_by_job_id = {m.job_id: m for m in match_rows}

    items = []
    for job in jobs:
        schema = JobSchema.model_validate(job)
        match = matches_by_job_id.get(job.id)
        if match is not None:
            schema.match = MatchResult.model_validate(match)
        items.append(schema)
    return JobListResponse(items=items, total=total)


@router.get("/jobs/search", response_model=ExternalJobsSearchResponse)
async def search_jobs(
    provider: str = Query(
        "himalayas",
        # Derived from the registry — a hand-typed regex here could accept a
        # provider that does not exist, or reject one that does.
        pattern=PROVIDER_NAMES_PATTERN,
    ),
    q: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    experience_level_filter: Optional[str] = Query(
        None, alias="experience_level", pattern="^(internship|entry|mid|senior|lead)$"
    ),
    remote_type_filter: Optional[str] = Query(None, alias="remote_type", pattern="^(remote|hybrid|onsite)$"),
    country: Optional[str] = Query(None),
    worldwide: Optional[bool] = Query(None),
    seniority: Optional[str] = Query(None),
    employment_type: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    current_user: User = Depends(get_current_user),
) -> ExternalJobsSearchResponse:
    """Live-search one provider. Nothing is persisted — pick a
    result and call POST /jobs/search/import to add it to `jobs`.

    See GET /jobs/search/aggregate to query every provider in one call,
    which is what Discover uses by default. adzuna/usajobs/serpapi
    require their own API keys (see .env) — calling them without keys
    configured returns a 502.
    """
    spec = get_provider(provider)
    params = SearchParams(
        q=q,
        location=location,
        experience_level_filter=experience_level_filter,
        remote_type_filter=remote_type_filter,
        category=category,
        page=page,
        country=country,
        worldwide=worldwide,
        seniority=seniority,
        employment_type=employment_type,
        sort=sort,
    )
    try:
        data = await spec.search(params)
    except ProviderUnavailable as exc:
        # The circuit breaker is open: this source has failed repeatedly and is
        # being skipped on purpose. 503 + Retry-After, not 502 — the request was
        # fine, the upstream is resting, and saying so lets a client back off
        # instead of hammering.
        raise HTTPException(
            status_code=503,
            detail=str(exc),
            headers={"Retry-After": "120"},
        ) from exc
    except spec.error_cls as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    results = [ExternalJobResult(**r) for r in normalize_results(spec, data["results"])]
    # Written here, where the normalized results are already in hand, so
    # "Agregar a la cola" still works after a restart empties the connector's
    # own in-memory copy. Dumped in JSON mode: the column is JSONB, and
    # `posted_at` is a datetime until it is told otherwise.
    await result_cache.remember(provider, [r.model_dump(mode="json") for r in results])
    has_more = bool(data.get("has_more"))
    return ExternalJobsSearchResponse(
        provider=provider,
        results=results,
        page=page + 1 if has_more else None,
        has_more=has_more,
    )


async def _run_search_provider(
    provider: str,
    q: Optional[str],
    location: Optional[str],
    experience_level_filter: Optional[str],
    remote_type_filter: Optional[str],
    category: Optional[str],
) -> tuple[str, list[ExternalJobResult], Optional[str]]:
    """Runs one provider search and normalizes both its results and any
    failure into a uniform (provider, results, error) tuple, so one
    provider erroring — including a keyed provider whose credentials
    aren't configured — never breaks the others in the aggregate fan-out.

    For a quota-limited provider (see app.services.api_budget), this first
    checks/consumes today's call budget — once the daily cap is hit, it
    returns an empty result with an explanatory error instead of ever
    reaching the network, same shape as any other provider failure."""
    if not await api_budget.try_consume_budget(provider):
        return provider, [], "Límite diario de llamadas alcanzado para proteger la cuota mensual — se reintenta mañana."
    try:
        spec = get_provider(provider)
    except KeyError:
        return provider, [], f"Unknown provider '{provider}'."

    try:
        data = await spec.search(
            SearchParams(
                q=q,
                location=location,
                experience_level_filter=experience_level_filter,
                remote_type_filter=remote_type_filter,
                category=category,
            )
        )
    except Exception as exc:  # noqa: BLE001 - any provider failure is reported, never raised
        return provider, [], str(exc)

    results = [ExternalJobResult(**r) for r in normalize_results(spec, data["results"])]
    # Every provider is asked for the work type, and several answer with
    # postings that contradict it: a remote search led with "Hybrid - San
    # Francisco, New York City, Austin", then a Berlin and a Köln role. The
    # posting's own words win over the source's filter — the same rule
    # linkedin_jobs already applies to its cards. A posting that says nothing
    # about where the work happens is left alone rather than guessed at.
    if remote_type_filter:
        results = [
            r
            for r in results
            if (_extract_remote_type(f"{r.title} {r.location or ''}") or remote_type_filter)
            == remote_type_filter
        ]
    # After the filter, not before: a result the user never sees is a result
    # they cannot import. Also covers the stragglers — a slow provider whose
    # task outlives its own request still leaves its results importable.
    await result_cache.remember(provider, [r.model_dump(mode="json") for r in results])
    return provider, results, None


def _aggregate_sort_key(result: ExternalJobResult) -> datetime:
    posted_at = result.posted_at
    if posted_at is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if posted_at.tzinfo is None:
        return posted_at.replace(tzinfo=timezone.utc)
    return posted_at


# The aggregate used to wait for its slowest provider, and a slow upstream can
# take up to its 20-30s httpx timeout — while the frontend gives up at 20s
# (REQUEST_TIMEOUT_MS). Every retry then started another full fan-out on top of
# the unfinished ones, so the next attempt was slower still. The deadline
# answers with whatever finished; the rest are NOT cancelled, so a slow feed
# still fills its provider cache and the next search gets it instantly. The
# message keeps "segundo plano" so Discover shows its neutral "buscando…" chip.
_AGGREGATE_DEADLINE_SECONDS = 12
_STILL_LOADING = "Tardó en responder; sigue cargando en segundo plano para la próxima búsqueda."
# Strong references: the event loop only holds tasks weakly, and a pending one
# with no other reference can be garbage-collected mid-request.
_stragglers: set[asyncio.Task] = set()


@router.get("/jobs/search/aggregate", response_model=AggregateSearchResponse)
@limiter.limit("10/minute")
async def search_jobs_aggregate(
    request: Request,
    q: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    experience_level_filter: Optional[str] = Query(
        None, alias="experience_level", pattern="^(internship|entry|mid|senior|lead)$"
    ),
    remote_type_filter: Optional[str] = Query(
        "remote", alias="remote_type", pattern="^(remote|hybrid|onsite)$"
    ),
    category: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
) -> AggregateSearchResponse:
    """Fans out to every job-search provider at once (Himalayas, Arbeitnow,
    Remotive, Jobicy, RemoteJobs.org, The Muse, We Work Remotely, Hacker
    News, Get on Board, LinkedIn, plus Adzuna/USAJobs/SerpApi
    whenever their keys are set in .env) and merges the results into one
    list, newest first — this is what the Discover tab's "search all
    sources" action calls. A provider
    that errors — including a keyed provider with no credentials
    configured — doesn't take the others down with it: its failure shows
    up in `sources` instead of the result list. `location` is purely
    geographic (e.g. "Mexico"); `remote_type` (remote/hybrid/onsite) is
    independent and defaults to "remote" to preserve the historical
    default of showing only remote-friendly postings when no filters are
    set."""
    tasks = {
        provider: asyncio.create_task(
            _run_search_provider(provider, q, location, experience_level_filter, remote_type_filter, category)
        )
        for provider in _SEARCH_PROVIDERS
    }
    await asyncio.wait(tasks.values(), timeout=_AGGREGATE_DEADLINE_SECONDS)

    outcomes = []
    for provider, task in tasks.items():
        if task.done():
            # _run_search_provider never raises — failures come back as its error.
            outcomes.append(task.result())
        else:
            _stragglers.add(task)
            task.add_done_callback(_stragglers.discard)
            outcomes.append((provider, [], _STILL_LOADING))

    all_results: list[ExternalJobResult] = []
    sources: list[AggregateSourceStatus] = []
    for provider, results, error in outcomes:
        all_results.extend(results)
        sources.append(AggregateSourceStatus(provider=provider, count=len(results), error=error))

    all_results.sort(key=_aggregate_sort_key, reverse=True)
    # Sort first, dedupe second: the providers overlap heavily (one vacancy
    # commonly appears on three or four of them), and deduping the sorted
    # list means the copy that survives is the newest one. Per-provider
    # `sources` counts stay pre-dedupe on purpose — they report what each
    # provider returned, which is what makes them useful for spotting a
    # provider that quietly went empty.
    all_results = dedupe_external_results(all_results)
    return AggregateSearchResponse(results=all_results, sources=sources)


async def _get_or_create_external_job(
    cached: dict, source: str, user_id: UUID, db: AsyncSession
) -> tuple[Job, bool]:
    """Creates a `jobs` row from a normalized external search result, or
    returns the existing one if this source_url was already imported by
    anyone. Returns (job, created) — shared by the manual "Add to queue"
    import and the CV-upload auto-import."""
    if cached.get("source_url"):
        existing = await db.execute(select(Job).where(Job.source_url == cached["source_url"]))
        existing_job = existing.scalar_one_or_none()
        if existing_job is not None:
            return existing_job, False

    job = Job(
        imported_by=user_id,
        source=JobSource(source),
        source_url=cached.get("source_url"),
        title=cached["title"],
        company=cached["company"],
        location=cached.get("location"),
        remote_type=cached.get("remote_type"),
        employment_type=cached.get("employment_type"),
        seniority=cached.get("seniority"),
        description=cached["description"],
        requirements=cached.get("requirements") or [],
        responsibilities=cached.get("responsibilities") or [],
        skills_required=cached.get("skills_required") or [],
        salary_min=cached.get("salary_min"),
        salary_max=cached.get("salary_max"),
        salary_currency=cached.get("salary_currency"),
        posted_at=cached.get("posted_at"),
        deadline=cached.get("deadline"),
    )
    if cached.get("apply_url"):
        # Los tableros de ATS ya traen el formulario: no hace falta que
        # run_daily_sweep lo busque luego (apply_checked_at queda puesto).
        job.apply_url = cached["apply_url"]
        job.apply_ats = cached.get("apply_ats") or detect_ats(cached["apply_url"])
        job.apply_checked_at = datetime.now(timezone.utc)
    db.add(job)
    try:
        await db.commit()
    except IntegrityError:
        # Lost the race: another request inserted this source_url between our
        # SELECT above and this INSERT. Narrowed from `except Exception` so a
        # connection drop or a bad value is no longer silently reinterpreted
        # as "someone else already imported it".
        await db.rollback()
        if cached.get("source_url"):
            existing = await db.execute(select(Job).where(Job.source_url == cached["source_url"]))
            existing_job = existing.scalar_one_or_none()
            if existing_job is not None:
                return existing_job, False
        raise
    await db.refresh(job)
    return job, True


@router.post("/jobs/search/import", response_model=JobSchema, status_code=status.HTTP_201_CREATED)
async def import_external_job(
    payload: ExternalJobImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobSchema:
    """Persist an external search result (found via GET /jobs/search) as a
    `jobs` row. Rebuilds it from the normalized result the search already
    returned rather than querying the provider a second time — first from
    that connector's in-memory copy, then from external_job_cache, which is
    the one that survives a restart."""
    if payload.source not in _SEARCH_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"Unknown source '{payload.source}'.")

    # Was a 15-entry dict repeated here. Forgetting to add a new provider to
    # it left search working while "Add to queue" raised KeyError -> 500.
    cached = get_provider(payload.source).get_cached(payload.external_id)
    if cached is None:
        # The connector's dict is emptied by every restart and by its own
        # 15-minute TTL, which is how a result still on screen could answer
        # "expired". The table outlives the process — see
        # app.services.external_jobs.result_cache.
        stored = await result_cache.get(payload.source, payload.external_id)
        if stored is not None:
            # Back through the schema: it restores the real types the JSONB
            # copy flattened (`posted_at` above all, which goes into a
            # timestamptz column), and rejects a payload written by an older
            # build whose shape no longer fits.
            try:
                cached = ExternalJobResult(**stored).model_dump()
            except ValidationError:
                logger.info("stale cached payload for %s/%s", payload.source, payload.external_id)
                cached = None
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail="This search result has expired — run the search again and import it right away.",
        )

    try:
        job, _created = await _get_or_create_external_job(cached, payload.source, current_user.id, db)
    except IntegrityError as exc:
        # Only a real uniqueness conflict means "already imported". This used
        # to be a bare `except Exception`, so a dropped database connection, a
        # value too long for its column or an invalid enum all reported
        # "This job was already imported." — sending you to look for a row
        # that was never written. Everything else now surfaces as a 500 and
        # gets recorded by error_middleware, which is where it can be found.
        await db.rollback()
        logger.info("import conflict for %s/%s: %s", payload.source, payload.external_id, exc.orig)
        raise HTTPException(status_code=409, detail="This job was already imported.") from exc
    await _ensure_match(job, current_user.id, db)
    return await _attach_match(job, current_user.id, db)


#: Un titular de perfil es un cartel, no un termino de busqueda. Se parte por
#: estos separadores para sacar los puestos que contiene.
_HEADLINE_SPLIT = re.compile(r"\s*[|/·•;]\s*|\s+[-–—]\s+|\s*,\s*|\s+&\s+|\s+\+\s+")

#: Palabras que adornan un titular y estrechan la busqueda sin aportar nada:
#: ninguna oferta se titula "Senior Aspiring Backend Engineer".
_HEADLINE_NOISE = {
    "senior", "junior", "lead", "principal", "staff", "aspiring", "experienced",
    "passionate", "results-driven", "freelance", "consultant", "especialista",
    "profesional", "apasionado", "con", "en", "de", "y", "and", "applied",
}

#: Cuatro palabras es lo mas largo que la mayoria de los portales trata como
#: una consulta y no como una frase literal que no encuentra nada.
_MAX_TERM_WORDS = 4


def _clean_search_term(raw: str) -> Optional[str]:
    """Convierte un trozo de titular en algo que un portal sepa buscar."""
    words = [w for w in re.split(r"\s+", (raw or "").strip()) if w]
    words = [w.strip("().,:;\"'") for w in words]
    words = [w for w in words if w and w.lower() not in _HEADLINE_NOISE]
    if not words:
        return None
    term = " ".join(words[:_MAX_TERM_WORDS])
    return term if len(term) >= 3 else None


def _profile_search_terms(profile: CareerProfile) -> list[str]:
    """Terminos de busqueda cortos sacados del perfil, de mas a menos preciso.

    Antes esto devolvia UN termino y era el titular entero, tal cual. Medido
    contra las 12 fuentes gratuitas en el mismo instante, con el mismo codigo:

        "Computer Science Engineer | Software Engineer | Backend, Full-Stack
         & Applied AI"  ->  25 resultados, 2 fuentes
        "Software Engineer"                              -> 276 resultados, 12 fuentes
        "backend"                                        -> 287 resultados, 12 fuentes

    Diez de las doce devolvian CERO y reportaban OK, porque la mayoria trata
    `q` como una frase: un titular de 79 caracteres con barras y ampersands no
    coincide con ninguna oferta. Jobicy directamente contestaba 400. No era un
    problema de las APIs ni de sus cuotas -- era la consulta.

    Se devuelve una lista y no un solo termino porque el titular suele nombrar
    varios puestos que la persona aceptaria, y quedarse con el primero tira los
    demas. El barrido usa el siguiente solo si el anterior no lleno la cola,
    asi que no cuesta llamadas de mas cuando el primero basta.
    """
    terms: list[str] = []

    def add(candidate: Optional[str]) -> None:
        cleaned = _clean_search_term(candidate or "")
        if cleaned and cleaned.lower() not in {t.lower() for t in terms}:
            terms.append(cleaned)

    for segment in _HEADLINE_SPLIT.split(profile.headline or ""):
        add(segment)
    for entry in profile.experience or []:
        add((entry or {}).get("title"))
    for skill in (profile.skills or [])[:3]:
        if isinstance(skill, dict):
            add(skill.get("name"))

    return terms[:4]


def _profile_search_query(profile: CareerProfile) -> Optional[str]:
    """El mejor termino unico. Se conserva para quien solo necesita uno."""
    terms = _profile_search_terms(profile)
    return terms[0] if terms else None


_HOME_QUEUE_TARGET = 30  # Home's swipe queue is topped up to this many undecided matches, never left to grow past it.
_AUTO_IMPORT_LIMIT = 20  # Hard ceiling per sweep regardless of queue headroom, so one run can't dump 30 at once.


async def _undecided_queue_size(user_id: UUID, db: AsyncSession) -> int:
    """How many jobs are currently sitting in this user's Home queue —
    matched but not yet swiped on. Same shape as GET /matches' own count
    query, kept separate since that endpoint also supports a min_score
    filter this one doesn't need."""
    decided_job_ids_subq = select(Application.job_id).where(Application.user_id == user_id)
    count_stmt = (
        select(func.count())
        .select_from(JobMatch)
        .where(JobMatch.user_id == user_id, JobMatch.job_id.not_in(decided_job_ids_subq))
    )
    return (await db.execute(count_stmt)).scalar_one()


async def run_auto_import_for_user(user: User, db: AsyncSession) -> AutoImportResponse:
    """Searches every no-auth provider using the saved career profile
    (headline, most recent role, or top skills) and imports the newest
    matches straight into `jobs` with a computed match score — this is
    what runs right after a CV-derived profile is saved, on every pull-to-
    refresh, and on the every-2-hours scheduled sweep, so Home's swipe
    queue has something to show without the user having to visit Discover
    first. Only genuinely new postings are counted/matched; ones already
    in the database (by source_url) are left alone.

    Tops the queue up to `_HOME_QUEUE_TARGET` (30) rather than always
    adding up to `_AUTO_IMPORT_LIMIT` more — a user who swipes slower than
    the 2-hour sweep would otherwise see the queue grow without bound;
    this keeps it capped so there's always a fresh batch waiting without
    ever overflowing.

    Extracted from the route handler below so the same logic can also run
    unattended — see app/scripts/run_daily_sweep.py, invoked on a schedule
    (scripts/install-job-sweep-schedule.ps1) so new matches show up (with a
    push notification) even if the app was never opened that day."""
    profile = (
        await db.execute(select(CareerProfile).where(CareerProfile.user_id == user.id))
    ).scalar_one_or_none()
    # SweepNotReady, not HTTPException: run_daily_sweep.py calls this on a
    # schedule with no request in sight, and a user without a profile is a
    # normal thing to skip there, not a 400 nobody is listening for.
    if profile is None:
        raise SweepNotReady("Save your career profile before auto-searching for matches.")

    terms = _profile_search_terms(profile)
    q = terms[0] if terms else None
    if not q:
        raise SweepNotReady(
            "Add a headline, a recent role, or a few skills to your profile first "
            "so we know what to search for."
        )

    current_queue_size = await _undecided_queue_size(user.id, db)
    room = max(0, _HOME_QUEUE_TARGET - current_queue_size)
    import_limit = min(room, _AUTO_IMPORT_LIMIT)

    if import_limit == 0:
        return AutoImportResponse(imported=0, query=q, sources=[])

    # Varios terminos, pero solo los que hagan falta. El primero se lanza a
    # todas las fuentes; los siguientes solo a las gratuitas, y solo si el
    # anterior no lleno la cola -- asi explorar mas no gasta cuota de adzuna
    # ni de serpapi, que es justo lo que hay que proteger.
    #
    # Esto es tambien la respuesta a "recargo y no trae nada nuevo": antes
    # siempre se preguntaba lo mismo, asi que una vez importada esa primera
    # pagina no habia mas que traer hasta que los portales publicaran algo.
    all_results: list[ExternalJobResult] = []
    sources: list[AggregateSourceStatus] = []
    seen_external: set[tuple[str, str]] = set()
    used_terms: list[str] = []

    for index, term in enumerate(terms):
        providers = _SEARCH_PROVIDERS if index == 0 else [
            p for p in _SEARCH_PROVIDERS if p in _NO_AUTH_PROVIDERS
        ]
        outcomes = await asyncio.gather(
            *[_run_search_provider(p, term, None, None, None, None) for p in providers]
        )
        used_terms.append(term)
        nuevos = 0
        for provider, results, error in outcomes:
            for result in results:
                key = (result.source, result.external_id)
                if key in seen_external:
                    continue
                seen_external.add(key)
                all_results.append(result)
                nuevos += 1
            sources.append(
                AggregateSourceStatus(
                    provider=provider if index == 0 else f"{provider} ({term})",
                    count=len(results),
                    error=error,
                )
            )
        # Con holgura de sobra sobre lo que caben, no hace falta seguir
        # preguntando: el resto se descartaria igual por el tope de la cola.
        if len(all_results) >= import_limit * 3:
            break
        if nuevos == 0 and index > 0:
            # Un termino que no aporta nada nuevo tampoco lo hara el siguiente
            # si el perfil es estrecho; se para en vez de recorrerlos todos.
            break

    all_results.sort(key=_aggregate_sort_key, reverse=True)
    # Matters even more here than in the search endpoint: without it the
    # sweep imports each board's copy of one vacancy as its own `jobs` row,
    # so Home asks the user to swipe on the same job three times. The
    # existing source_url check in _get_or_create_external_job only catches
    # copies that happen to share a URL.
    all_results = dedupe_external_results(all_results)

    imported = 0
    skipped = 0
    # Walk the FULL sorted list (not a pre-sliced all_results[:import_limit])
    # and stop once import_limit NEW jobs are actually in — slicing first
    # was the bug: across repeated 2-hour sweeps against the same
    # profile-based query, the newest-first top of the list is dominated by
    # postings already imported in earlier sweeps, so a pre-slice mostly
    # re-examined duplicates and imported far fewer than import_limit even
    # though plenty of never-seen postings existed further down the list.
    for result in all_results:
        if imported >= import_limit:
            break
        try:
            job, created = await _get_or_create_external_job(
                result.model_dump(), result.source, user.id, db
            )
        except Exception as exc:  # noqa: BLE001 — one bad posting must not end the sweep
            # Used to be a bare `continue`: a posting that could not be stored
            # vanished with no count and no log, so "the sweep found 30 and
            # imported 4" had no explanation anywhere.
            skipped += 1
            logger.warning(
                "sweep: se omitio %s/%s — %s: %s",
                result.source,
                result.external_id,
                type(exc).__name__,
                exc,
            )
            await db.rollback()
            continue
        if not created:
            continue
        # use_llm=False: this loop can run once per newly-discovered job in
        # a single sweep — keep it on the free, offline semantic scorer
        # rather than firing one Anthropic call per job serially. On-demand
        # single-job matches (_ensure_match above, GET /jobs/{id}/match)
        # keep the higher-quality LLM default.
        await compute_and_persist_match(profile, job, user.id, db, use_llm=False)
        imported += 1

    if imported > 0 and push_notifications.is_configured():
        from firebase_admin import messaging

        tokens = (
            await db.execute(select(DeviceToken.token).where(DeviceToken.user_id == user.id))
        ).scalars().all()
        plural = "s" if imported != 1 else ""
        dead_tokens: list[str] = []
        for device_token in tokens:
            try:
                push_notifications.send_push(
                    device_token,
                    "JobPilot",
                    f"Encontramos {imported} vacante{plural} nueva{plural} que hacen match — ya están en tu cola.",
                )
            except messaging.UnregisteredError:
                dead_tokens.append(device_token)
        if dead_tokens:
            # A dead token failing here must never affect imported/matches
            # already committed above — this cleanup is best-effort and
            # isolated from the rest of the sweep's outcome.
            await db.execute(delete(DeviceToken).where(DeviceToken.token.in_(dead_tokens)))
            await db.commit()

    if skipped:
        # Surfaced in the same place the per-source errors are, so the count
        # the user sees adds up instead of quietly not matching.
        sources.append(
            AggregateSourceStatus(
                provider="import",
                count=0,
                error=f"{skipped} vacante(s) no se pudieron guardar — ver los logs del backend.",
            )
        )

    return AutoImportResponse(imported=imported, query=" · ".join(used_terms), sources=sources)


@router.post("/jobs/search/auto-import", response_model=AutoImportResponse)
@limiter.limit("10/minute")
async def auto_import_matching_jobs(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AutoImportResponse:
    # The HTTP layer is where a domain error becomes a status code. The
    # service itself stays usable from run_daily_sweep.py, which has no
    # request to answer.
    try:
        return await run_auto_import_for_user(current_user, db)
    except SweepNotReady as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs/{job_id}", response_model=JobSchema)
async def get_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobSchema:
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return await _attach_match(job, current_user.id, db)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    # `jobs` is a shared table on purpose — two users importing the same
    # source_url get the same row, which is what makes dedupe work. But that
    # made DELETE the one global write with no owner: any authenticated user
    # could remove a row out from under everyone else. Deleting is now
    # restricted to rows this user imported; rows with no importer (older
    # data, before imported_by was populated) stay deletable so existing
    # queues don't become impossible to clean up.
    result = await db.execute(
        select(Job).where(
            Job.id == job_id,
            or_(Job.imported_by == current_user.id, Job.imported_by.is_(None)),
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        # Deliberately the same 404 whether the row is missing or belongs to
        # someone else — a distinct 403 would confirm the id exists.
        raise HTTPException(status_code=404, detail="Job not found.")
    await db.delete(job)
    await db.commit()
