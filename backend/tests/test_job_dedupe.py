from app.schemas.job import ExternalJobResult
from app.services.job_dedupe import dedupe_external_results


def result(
    *,
    source="himalayas",
    external_id="1",
    title="Senior Backend Engineer",
    company="Acme",
    location="Remote",
    source_url=None,
    description="",
    salary_min=None,
):
    return ExternalJobResult(
        external_id=external_id,
        source=source,
        title=title,
        company=company,
        location=location,
        source_url=source_url,
        description=description,
        requirements=[],
        skills_required=[],
        salary_min=salary_min,
    )


def test_collapses_same_posting_indexed_by_several_boards():
    """The case this exists for: one vacancy, four providers."""
    results = [
        result(source="himalayas", external_id="h1"),
        result(source="remotive", external_id="r1"),
        result(source="jobicy", external_id="j1"),
    ]
    assert len(dedupe_external_results(results)) == 1


def test_matches_on_apply_url_even_when_the_wording_differs():
    """Boards rewrite titles ("Sr." vs "Senior") but link the same ATS page."""
    results = [
        result(title="Senior Backend Engineer", source_url="https://boards.greenhouse.io/acme/jobs/42"),
        result(title="Sr. Backend Eng.", company="Acme Inc.", source_url="https://boards.greenhouse.io/acme/jobs/42"),
    ]
    assert len(dedupe_external_results(results)) == 1


def test_ignores_tracking_parameters_and_trailing_slashes_in_the_url():
    results = [
        result(company="A", title="X", source_url="https://jobs.example.com/a/1"),
        result(company="B", title="Y", source_url="https://www.jobs.example.com/a/1/?utm_source=remotive&ref=feed"),
    ]
    assert len(dedupe_external_results(results)) == 1


def test_treats_every_spelling_of_remote_as_one_location():
    results = [
        result(location="Remote"),
        result(location="Worldwide"),
        result(location="Anywhere"),
        result(location=None),
    ]
    assert len(dedupe_external_results(results)) == 1


def test_keeps_the_same_role_in_genuinely_different_cities():
    """The main over-merge risk: one company hiring the same title in two
    places, written up separately, is two jobs — so with no description to
    prove otherwise they stay apart."""
    results = [
        result(location="Berlin, Germany"),
        result(location="New York, NY"),
    ]
    assert len(dedupe_external_results(results)) == 2


# The pattern that actually floods the queue, found by running the real
# provider fan-out: one vacancy re-posted across every town in a metro area,
# each with its own ad URL and its own location, all sharing one description.
_FANOUT_DESCRIPTION = (
    "We are looking for a senior software engineer to join our avionics team. "
    "You will design, build and maintain mission-critical systems, working "
    "closely with hardware engineers and product owners across the programme."
)


def test_collapses_one_job_fanned_out_across_a_metro_area():
    towns = [
        "East Boston, Suffolk County",
        "Woonsocket, Providence County",
        "West Somerville, Middlesex County",
        "Hope, Providence County",
    ]
    results = [
        result(external_id=f"a{i}", location=town, source_url=f"https://adzuna.com/land/ad/{i}", description=_FANOUT_DESCRIPTION)
        for i, town in enumerate(towns)
    ]

    deduped = dedupe_external_results(results)

    assert len(deduped) == 1
    # The other towns must still be visible somewhere, or collapsing would
    # make a metro-wide posting look like a single-town one.
    assert "+3 ubicaciones más" in deduped[0].location
    assert deduped[0].location.startswith("East Boston")


def test_a_single_merged_location_reads_in_singular():
    results = [
        result(external_id="a", location="Boston, MA", source_url="https://x.com/1", description=_FANOUT_DESCRIPTION),
        result(external_id="b", location="Cambridge, MA", source_url="https://x.com/2", description=_FANOUT_DESCRIPTION),
    ]
    deduped = dedupe_external_results(results)
    assert len(deduped) == 1
    assert "+1 ubicación más" in deduped[0].location


def test_repeat_ads_for_one_town_count_as_one_location():
    """Three ads for the same town shouldn't claim the job spans three
    places — the annotation counts locations, not copies."""
    results = [
        result(external_id=f"a{i}", location="Boston, MA", source_url=f"https://x.com/{i}", description=_FANOUT_DESCRIPTION)
        for i in range(3)
    ]
    deduped = dedupe_external_results(results)
    assert len(deduped) == 1
    assert "ubicaci" not in deduped[0].location  # no annotation at all


def test_different_cities_with_different_descriptions_stay_apart():
    """Two real openings are written separately, and that's the signal the
    location-agnostic rule keys off — so it must not fire here."""
    results = [
        result(location="Berlin, Germany", source_url="https://x.com/1", description=_FANOUT_DESCRIPTION),
        result(
            location="New York, NY",
            source_url="https://x.com/2",
            description="Join our New York office to lead a brand new payments team. "
            "This role focuses on regulatory compliance and partner integrations "
            "across the Americas, and reports directly to the VP of Engineering.",
        ),
    ]
    assert len(dedupe_external_results(results)) == 2


def test_short_identical_descriptions_are_not_enough_to_merge_across_cities():
    """A truncated stub repeated by a board proves nothing about sameness."""
    results = [
        result(location="Berlin, Germany", source_url="https://x.com/1", description="Great role. Apply now."),
        result(location="New York, NY", source_url="https://x.com/2", description="Great role. Apply now."),
    ]
    assert len(dedupe_external_results(results)) == 2


def test_keeps_different_roles_at_the_same_company():
    results = [
        result(title="Backend Engineer"),
        result(title="Frontend Engineer"),
    ]
    assert len(dedupe_external_results(results)) == 2


def test_keeps_the_same_title_at_different_companies():
    results = [
        result(company="Acme"),
        result(company="Globex"),
    ]
    assert len(dedupe_external_results(results)) == 2


def test_keeps_the_richer_copy_of_a_duplicate():
    """Providers carry different amounts of detail for one posting; losing
    the salary band because the barer copy sorted first would be a silent
    regression in what the user sees."""
    bare = result(source="himalayas", external_id="h1", description="Short.")
    rich = result(
        source="remotive",
        external_id="r1",
        description="A much longer description with the actual detail.",
        salary_min=120000,
    )

    deduped = dedupe_external_results([bare, rich])

    assert len(deduped) == 1
    assert deduped[0].salary_min == 120000
    assert deduped[0].source == "remotive"


def test_keeps_the_surviving_copy_in_the_original_position():
    """Callers sort by posted date before deduping and rely on that order
    afterwards, so a duplicate must never promote an entry up the list."""
    first = result(company="Zeta", title="Data Engineer")
    second = result(company="Acme", title="Backend Engineer", description="short")
    third = result(company="Acme", title="Backend Engineer", description="a much longer one")

    deduped = dedupe_external_results([first, second, third])

    assert len(deduped) == 2
    assert deduped[0].company == "Zeta"
    # The richer third copy won, but stays in the second slot the earlier
    # duplicate already held.
    assert deduped[1].description == "a much longer one"


def test_does_not_merge_rows_that_are_too_empty_to_compare():
    """A blank company is not evidence of anything — two such rows must not
    collapse into one just because both are blank."""
    results = [
        result(company="", title="Engineer", source_url=None, external_id="a"),
        result(company="", title="Engineer", source_url=None, external_id="b"),
    ]
    assert len(dedupe_external_results(results)) == 2


def test_empty_input():
    assert dedupe_external_results([]) == []
