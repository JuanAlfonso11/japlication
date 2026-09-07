from app.services.skill_gaps import aggregate_skill_gaps, summarize


def test_counts_how_many_jobs_wanted_each_missing_skill():
    gaps, total = aggregate_skill_gaps(
        [
            ["Kubernetes", "Go"],
            ["Kubernetes", "Terraform"],
            ["Kubernetes"],
            ["Go"],
        ]
    )

    assert total == 4
    assert gaps[0]["skill"] == "Kubernetes"
    assert gaps[0]["job_count"] == 3
    assert gaps[0]["percentage"] == 75
    assert gaps[1]["skill"] == "Go"
    assert gaps[1]["job_count"] == 2


def test_drops_skills_that_only_showed_up_once():
    """A one-off tool is an anecdote, and reorganizing your learning around
    it would be actively bad advice."""
    gaps, _ = aggregate_skill_gaps([["Kubernetes", "COBOL"], ["Kubernetes"]])
    assert [g["skill"] for g in gaps] == ["Kubernetes"]


def test_matches_the_same_skill_across_spellings():
    gaps, _ = aggregate_skill_gaps([["kubernetes"], ["Kubernetes"], ["  KUBERNETES  "]])
    assert len(gaps) == 1
    assert gaps[0]["job_count"] == 3


def test_prefers_the_properly_capitalized_label():
    """Job posts write real product names properly and lowercase them by
    accident, so the nicer spelling is the more likely correct one."""
    gaps, _ = aggregate_skill_gaps([["postgresql"], ["PostgreSQL"]])
    assert gaps[0]["skill"] == "PostgreSQL"


def test_one_job_listing_a_skill_twice_still_counts_once():
    """Otherwise a single verbose posting could outvote a real pattern
    across many jobs."""
    gaps, _ = aggregate_skill_gaps([["Go", "go", "GO"], ["Go"]])
    assert gaps[0]["job_count"] == 2


def test_ignores_blank_entries():
    gaps, total = aggregate_skill_gaps([["Go", "", "   "], ["Go"]])
    assert total == 2
    assert [g["skill"] for g in gaps] == ["Go"]


def test_respects_the_limit():
    jobs = [["a", "b", "c", "d", "e"], ["a", "b", "c", "d", "e"]]
    gaps, _ = aggregate_skill_gaps(jobs, limit=3)
    assert len(gaps) == 3


def test_no_jobs_at_all():
    gaps, total = aggregate_skill_gaps([])
    assert gaps == []
    assert total == 0
    assert summarize(gaps, total) is None


def test_jobs_with_no_gaps_are_still_counted_in_the_denominator():
    """A job you fully match must still lower the percentage — otherwise the
    number reads as 100% of everything."""
    gaps, total = aggregate_skill_gaps([["Go"], ["Go"], [], []])
    assert total == 4
    assert gaps[0]["percentage"] == 50


def test_summary_names_the_top_gap():
    gaps, total = aggregate_skill_gaps([["Kubernetes"], ["Kubernetes"], ["Go"], ["Go"]])
    text = summarize(gaps, total)
    assert text is not None
    assert "Kubernetes" in text
    assert "50%" in text
