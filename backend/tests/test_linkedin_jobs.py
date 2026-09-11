"""Tests for LinkedIn search through its public job pages.

The markup below is trimmed from real guest responses (2026-09-11). What's
worth pinning fails silently: a markup change parses to zero cards, a wrong
remote tag just shows the wrong badge, and a cache that doesn't hold turns
every Discover search into eleven requests to LinkedIn.
"""

import asyncio

import httpx
import pytest

from app.services import linkedin_jobs

CARD = """
<li><div class="base-card relative w-full base-search-card base-search-card--link job-search-card"
    data-entity-urn="urn:li:jobPosting:4463535890" data-row="1">
  <a class="base-card__full-link absolute top-0 right-0" href="https://do.linkedin.com/jobs/view/golang-developer-trabajo-remoto-at-bairesdev-4463535890?position=1&amp;pageNum=0">
    <span class="sr-only">Golang Developer - Trabajo Remoto</span>
  </a>
  <div class="base-search-card__info">
    <h3 class="base-search-card__title">
        Golang Developer - Trabajo Remoto
    </h3>
    <h4 class="base-search-card__subtitle">
      <a class="hidden-nested-link" href="https://www.linkedin.com/company/bairesdev?trk=public_jobs">
        BairesDev
      </a>
    </h4>
    <div class="base-search-card__metadata">
      <span class="job-search-card__location">
        Santo Domingo de Guzmán, Distrito Nacional, Dominican Republic
      </span>
      <div class="job-posting-benefits text-sm"><span class="job-posting-benefits__text">Be an early applicant</span></div>
      <time class="job-search-card__listdate" datetime="2026-09-08">
        3 days ago
      </time>
    </div>
  </div>
</div></li>
"""

POSTING = """
<section class="show-more-less-html" data-max-lines="5">
  <div class="show-more-less-html__markup show-more-less-html__markup--clamp-after-5
      relative overflow-hidden">
    <p>Golang Developer en BairesDev</p><p><br></p><p>¿Qué Buscamos?:</p><p>- Experiencia con bases de datos SQL y NoSQL</p><p>- Trabajo 100% remoto: trabaja desde tu casa o donde quieras.</p>
  </div>
</section>
<ul class="description__job-criteria-list">
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader">Seniority level</h3>
    <span class="description__job-criteria-text description__job-criteria-text--criteria">Mid-Senior level</span>
  </li>
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader">Employment type</h3>
    <span class="description__job-criteria-text description__job-criteria-text--criteria">Full-time</span>
  </li>
</ul>
"""


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(linkedin_jobs.settings, "LINKEDIN_LOCATION", "Worldwide")
    linkedin_jobs._query_cache.clear()
    linkedin_jobs._job_cache.clear()


def _serve(monkeypatch, handler):
    """Routes the service's HTTP client to `handler` instead of LinkedIn."""
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        linkedin_jobs.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )


def test_parse_cards_reads_a_real_card():
    [card] = linkedin_jobs.parse_cards(CARD)
    assert card["id"] == "4463535890"
    assert card["title"] == "Golang Developer - Trabajo Remoto"
    assert card["company"] == "BairesDev"
    assert card["location"] == "Santo Domingo de Guzmán, Distrito Nacional, Dominican Republic"
    assert card["url"] == "https://do.linkedin.com/jobs/view/golang-developer-trabajo-remoto-at-bairesdev-4463535890"
    assert (card["date"], card["date_text"]) == ("2026-09-08", "3 days ago")


def test_parse_posting_keeps_one_line_per_paragraph():
    posting = linkedin_jobs.parse_posting(POSTING)
    # parse_job_text_heuristic finds requirements line by line.
    assert "- Experiencia con bases de datos SQL y NoSQL" in posting["description"].split("\n")
    assert posting["seniority"] == "Mid-Senior level"
    assert posting["employment_type"] == "Full-time"


@pytest.mark.parametrize(
    "title,description,requested,expected",
    [
        # LinkedIn's own workplace-type filter is trusted when one was used.
        ("Backend Developer", "Nothing here says where the work happens.", "remote", "remote"),
        # A title that states its own work type wins over the filter.
        ("Backend Developer - Hybrid", "Two days a week in the office.", "remote", "hybrid"),
        # No filter: the same description scan every other source uses.
        ("Backend Developer", "This is a presencial role in Santiago.", None, "onsite"),
        ("Backend Developer", "Nothing here says where the work happens.", None, None),
    ],
)
def test_remote_tag(title, description, requested, expected):
    [card] = linkedin_jobs.parse_cards(CARD)
    job = linkedin_jobs._normalize({**card, "title": title}, {"description": description}, requested)
    assert job["remote_type"] == expected


def test_a_title_that_states_its_level_wins_over_linkedins_field():
    # Live results had "Senior ..." roles whose LinkedIn seniority field said Internship.
    [card] = linkedin_jobs.parse_cards(CARD)
    posting = {"description": "Build things.", "seniority": "Internship"}
    assert linkedin_jobs._normalize({**card, "title": "Senior Full-stack Engineer"}, posting, None)["seniority"] == "senior"
    # A title with no level of its own still takes LinkedIn's.
    assert linkedin_jobs._normalize(card, posting, None)["seniority"] == "internship"


def test_search_reads_linkedin_once_then_answers_from_cache(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/search"):
            assert request.url.params["keywords"] == "golang developer"
            assert request.url.params["f_WT"] == "2"
            return httpx.Response(200, text=CARD)
        return httpx.Response(200, text=POSTING)

    _serve(monkeypatch, handler)

    async def scenario():
        first = await linkedin_jobs.search_linkedin_jobs(q="Golang  Developer", remote_type_filter="remote")
        again = await linkedin_jobs.search_linkedin_jobs(q="golang developer", remote_type_filter="remote")
        return first, again

    first, again = asyncio.run(scenario())
    assert len(requests) == 2  # the search page and its one posting page; the repeat sends nothing
    assert first == again
    [job] = first["results"]
    assert (job["remote_type"], job["seniority"], job["employment_type"]) == ("remote", "senior", "full_time")
    # The aggregate sorts every source's posted_at together, so it must carry a timezone.
    assert job["posted_at"].tzinfo is not None
    assert linkedin_jobs.get_cached_result("4463535890")["company"] == "BairesDev"


def test_rate_limit_is_reported_and_not_cached(monkeypatch):
    _serve(monkeypatch, lambda request: httpx.Response(429))
    with pytest.raises(linkedin_jobs.LinkedInError, match="limitando"):
        asyncio.run(linkedin_jobs.search_linkedin_jobs(q="golang developer"))
    assert linkedin_jobs._query_cache == {}


def test_a_posting_page_that_fails_still_shows_its_card(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/search"):
            return httpx.Response(200, text=CARD)
        return httpx.Response(429)

    _serve(monkeypatch, handler)
    [job] = asyncio.run(linkedin_jobs.search_linkedin_jobs(q="golang developer"))["results"]
    assert job["title"] == "Golang Developer - Trabajo Remoto"
    assert job["description"] == "No description provided."


def test_empty_keyword_sends_no_request(monkeypatch):
    def handler(request):
        raise AssertionError("an empty search must not reach LinkedIn")

    _serve(monkeypatch, handler)
    assert asyncio.run(linkedin_jobs.search_linkedin_jobs(q="   ")) == {"results": [], "has_more": False}
