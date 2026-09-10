"""Tests for the LaTeX export.

Two failure modes matter here, and they are very different in cost.

An unescaped metacharacter is a *compile error*: the document produces no
PDF at all, and the user finds out in Overleaf rather than here. Every one
of `& % $ # _ { } ~ ^ \\` appears in real CVs — "R&D", "20% growth",
"$1.2M", "snake_case", "{JSON}" — so these are not exotic inputs.

The other is quieter: a LaTeX CV that compiles beautifully and parses
badly. Fancy CV classes use multi-column layouts, `tabular` for
positioning, and icon fonts where a glyph replaces the word "email". The
structural assertions below exist to keep this template plain.
"""

import pytest

from app.services.resume_latex import escape, render_resume_latex

CONTENT = {
    "summary": "Engineer with C# and AWS experience.",
    "skills": ["C#", "ASP.NET", "SQL Server"],
    "experience": [
        {
            "company": "PUCMM - Academic Projects",
            "title": "Software Developer",
            "start_date": "2022-01",
            "end_date": None,
            "location": "Santiago, RD",
            "bullets": ["Built mobile apps in C# with Xamarin."],
        }
    ],
    "education": [
        {
            "institution": "PUCMM",
            "degree": "Bachelor's Degree in Computer Science Engineering",
            "field": "Computer Science",
            "start_date": "2020",
            "end_date": None,
        }
    ],
}


def render(**overrides):
    kwargs = dict(
        full_name="Juan Alvarado",
        contact_info={"phone": "+1 829-619-8930", "city": "Santiago"},
        content=CONTENT,
        language="en",
        email="juan@example.com",
    )
    kwargs.update(overrides)
    return render_resume_latex(**kwargs)


# --- escaping ---------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("R&D", r"R\&D"),
        ("20% growth", r"20\% growth"),
        ("$1.2M", r"\$1.2M"),
        # '#' is harmless in body text but fatal inside a macro argument,
        # which is exactly where these strings end up.
        ("C#", r"C\#"),
        ("snake_case", r"snake\_case"),
        ("{JSON}", r"\{JSON\}"),
        ("a~b", r"a\textasciitilde{}b"),
        ("2^10", r"2\textasciicircum{}10"),
    ],
)
def test_escapes_characters_that_would_break_the_build(raw, expected):
    assert escape(raw) == expected


def test_backslash_is_escaped_first():
    """Escaping '&' before '\\' would turn "\\&" into "\\textbackslash{}&"
    and then re-escape the '&' inside the replacement — a corrupted document
    from a single stray backslash."""
    assert escape("a\\b") == r"a\textbackslash{}b"
    assert "\\&" not in escape("a\\b")


def test_a_bullet_full_of_metacharacters_still_produces_one_document():
    source = render(
        content={
            **CONTENT,
            "experience": [
                {
                    "company": "R&D Labs",
                    "title": "Dev",
                    "start_date": "2022",
                    "end_date": None,
                    "location": "",
                    "bullets": ["Cut costs 20% & saved $1.2M using snake_case {configs}"],
                }
            ],
        }
    )
    assert r"20\% \& saved \$1.2M" in source
    assert r"snake\_case \{configs\}" in source


# --- structure that keeps it parseable --------------------------------------


def test_document_is_complete_and_single_column():
    source = render()
    assert source.startswith("%")  # provenance comment
    assert "\\documentclass[11pt,letterpaper]{article}" in source
    assert source.rstrip().endswith("\\end{document}")
    # The things that break resume parsers, none of which belong here.
    for hostile in ("multicol", "tabular", "\\begin{table}", "fontawesome", "includegraphics"):
        assert hostile not in source, f"{hostile} makes the CV hard to parse"


def test_contact_line_leads_with_the_email():
    """Same rule as the PDF renderer: an ATS keys its record on the email,
    so it goes where a parser looks first."""
    source = render()
    header = source.split("\\end{center}")[0]
    assert "juan@example.com" in header
    assert header.index("juan@example.com") < header.index("829-619-8930")


def test_contact_links_lose_their_tracking_parameters():
    source = render(
        contact_info={
            "linkedin": "https://linkedin.com/in/juan?utm_source=share_via&utm_medium=android"
        }
    )
    assert "utm_source" not in source
    assert "linkedin.com/in/juan" in source


def test_section_headings_follow_the_language():
    english = render(language="en")
    spanish = render(language="es")
    assert "\\section*{SUMMARY}" in english
    assert "\\section*{RESUMEN PROFESIONAL}" in spanish
    assert "[english]{babel}" in english
    assert "[spanish]{babel}" in spanish


def test_an_ongoing_role_says_present_rather_than_nothing():
    assert "2022-01 -- Present" in render(language="en")
    assert "2022-01 -- Actualidad" in render(language="es")


def test_degree_does_not_repeat_the_field_it_already_names():
    source = render()
    assert "Engineering, Computer Science" not in source


def test_empty_sections_are_omitted_rather_than_left_as_bare_headings():
    source = render(content={"summary": "", "skills": [], "experience": [], "education": []})
    for label in ("SUMMARY", "SKILLS", "EXPERIENCE", "EDUCATION"):
        assert f"\\section*{{{label}}}" not in source
    assert "\\end{document}" in source
