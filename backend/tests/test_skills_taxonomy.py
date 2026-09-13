"""What the skills extractor must NOT find.

Every canonical name is registered as its own synonym, so single common
words matched ordinary prose: "Go" ended up a required skill on 46 of this
database's 196 postings, "REST APIs" on 48 and "C" on 54 (mostly from "C++"
and "C#", since the boundary guard treats "+" and "#" as separators). Those
phantom requirements then scored a perfect technical match against any
profile that happens to list Go or REST APIs.
"""

from app.services.skills_taxonomy import extract_skills_from_text, normalize_skill

PROSE = "The rest of the team will go to the spring offsite and share what they learn."


def test_plain_prose_extracts_nothing():
    assert extract_skills_from_text(PROSE) == []


def test_the_longer_spellings_still_match():
    found = extract_skills_from_text(
        "Build REST APIs in Golang, plus a Spring Boot service and some C programming."
    )
    assert set(found) >= {"REST APIs", "Go", "Spring Boot", "C"}


def test_cpp_and_csharp_do_not_also_report_c():
    found = extract_skills_from_text("We use C++ and C# across the platform.")
    assert "C++" in found
    assert "C#" in found
    assert "C" not in found


def test_an_explicitly_listed_skill_still_normalizes():
    """The guard is only about scanning free text: a posting (or profile)
    that lists "Go" as a skill outright still resolves to the canonical
    name, which is what the match engine compares."""
    assert normalize_skill("go") == "Go"
    assert normalize_skill("rest") == "REST APIs"
