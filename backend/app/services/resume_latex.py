"""Renders a resume_versions.content dict as a LaTeX source document.

WHY THIS TEMPLATE IS PLAIN ON PURPOSE
-------------------------------------
LaTeX CV templates are one of the most reliable ways to break an applicant
tracking system. The popular ones (moderncv's banking style, AltaCV, Deedy)
lean on multi-column layouts, `tabular` used for positioning, and icon
fonts where a glyph stands in for the word "email". A parser reading that
back gets columns interleaved line by line, contact details that extract as
private-use-area characters, and section headers it cannot recognise.

So this template deliberately keeps every property the direct-PDF renderer
already guarantees (see resume_pdf.py): one column, ordinary section
headings as real words, real selectable text, no tables, no graphics, no
icon fonts. It exists to give the document LaTeX's typography — better
spacing, hyphenation and justification — not a different layout.

Two more deliberate choices:

`\\sloppy` and a wide `\\emergencystretch`. A justified line that cannot
break is set as an overfull box, and the overflowing text can extract in
the wrong order. Letting TeX stretch spacing further than usual trades a
little visual evenness for a document that always extracts in reading
order.

Hyperlinks carry `hidelinks`. A coloured box around a URL is drawn by
`hyperref` as an annotation; some parsers read the annotation instead of
the text under it and end up with the URL twice, or with neither.
"""

from __future__ import annotations

from typing import Any

from app.services.profile_i18n import labels_for

#: Applied with str.translate, which makes exactly ONE pass and never
#: re-scans what it just emitted. Sequential str.replace calls cannot do
#: this correctly at any ordering: replacing "\" with "\textbackslash{}"
#: first still leaves those braces in the string for the later "{" and "}"
#: rules to escape, turning a single stray backslash into
#: "\textbackslash\{\}" — which compiles, and prints garbage.
_TRANSLATION = str.maketrans(
    {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
)


def escape(value: Any) -> str:
    """Makes arbitrary profile text safe to drop into a LaTeX document.

    Every one of these characters appears in real CVs — "C#" has none but
    "R&D", "20% growth", "$1.2M", "snake_case" and "{JSON}" all do, and an
    unescaped one is not a typo: it is a compile error, so the document
    produces no PDF at all.
    """
    return str(value or "").translate(_TRANSLATION)


def _clean_url(value: Any) -> str:
    """Same rule as the PDF renderer: a contact link needs no query string.

    Here it matters twice over — `%` and `&` are LaTeX metacharacters, and a
    tracking-laden URL is exactly where they turn up."""
    return str(value or "").strip().split("?", 1)[0]


def _url(raw: str) -> str:
    """A clickable link whose visible text is the URL without its scheme.

    `\\href` rather than `\\url`: `\\url` would print "https://" too, which
    is noise on a CV, and it breaks lines at characters that then extract
    with a stray hyphen."""
    cleaned = _clean_url(raw)
    if not cleaned:
        return ""
    shown = cleaned.split("://", 1)[-1]
    return f"\\href{{{escape(cleaned)}}}{{{escape(shown)}}}"


def _section(title: str, body: str) -> str:
    return f"\\section*{{{escape(title)}}}\n{body}\n"


def _experience_block(entries: list[dict[str, Any]], labels: dict[str, str]) -> str:
    out: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        header = " --- ".join(
            escape(part) for part in (entry.get("title"), entry.get("company")) if part
        )
        dates = " -- ".join(
            escape(part)
            for part in (entry.get("start_date"), entry.get("end_date") or labels["present"])
            if part
        )
        meta = "  |  ".join(part for part in (dates, escape(entry.get("location"))) if part)

        out.append(f"\\rolehead{{{header or escape(labels['role'])}}}")
        if meta:
            out.append(f"\\rolemeta{{{meta}}}")

        bullets = [b for b in (entry.get("bullets") or []) if str(b).strip()]
        if bullets:
            out.append("\\begin{itemize}")
            out.extend(f"  \\item {escape(b)}" for b in bullets)
            out.append("\\end{itemize}")
        out.append("")
    return "\n".join(out)


def _education_block(entries: list[dict[str, Any]], labels: dict[str, str]) -> str:
    out: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        degree = str(entry.get("degree") or "")
        field = str(entry.get("field") or "")
        # Same rule the PDF renderer uses: a degree that already names its
        # field must not say it twice.
        parts = [degree] if (field and field.lower() in degree.lower()) else [degree, field]
        line = ", ".join(escape(p) for p in parts if p)
        if entry.get("institution"):
            line = f"{line} --- {escape(entry['institution'])}" if line else escape(entry["institution"])
        end = entry.get("end_date") or (labels["present"] if entry.get("start_date") else None)
        span = " -- ".join(escape(p) for p in (entry.get("start_date"), end) if p)
        if span:
            line = f"{line} ({span})"
        if line:
            out.append(f"\\noindent {line}\\par")
    return "\n".join(out)


PREAMBLE = r"""% Generated by JobPilot. Single column, standard headings, real text --
% the layout properties an applicant tracking system needs to parse this
% correctly. See backend/app/services/resume_latex.py before restyling it.
\documentclass[11pt,letterpaper]{article}

\usepackage[utf8]{inputenc}
% lmodern BEFORE fontenc, and non-negotiable. T1 encoding with the default
% Computer Modern needs the EC fonts, which many installations do not have
% as Type 1 — pdflatex then renders them as BITMAPS. A bitmap font carries
% no reliable character mapping, so the text stops extracting: measured on
% this very document, the email came out as "arado@hotmail.com", the
% LinkedIn URL vanished, and the SUMMARY and EDUCATION headings were not
% found at all. Latin Modern is a real Type 1/OpenType face with full T1
% coverage, so nothing falls back to bitmaps.
\usepackage{lmodern}
\usepackage[T1]{fontenc}
\usepackage[LANGUAGE_OPTION]{babel}
\usepackage[margin=0.75in]{geometry}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{titlesec}
\usepackage{parskip}

% An unbreakable justified line becomes an overfull box, and overflowing
% text can extract out of order. Stretching further than TeX's default
% trades a little evenness for text that always reads back in order.
\sloppy
\emergencystretch=3em

\titleformat{\section}{\large\bfseries}{}{0pt}{}[\titlerule]
\titlespacing*{\section}{0pt}{12pt}{6pt}
\setlist[itemize]{leftmargin=1.2em, itemsep=2pt, topsep=3pt, parsep=0pt}
\pagestyle{empty}

\newcommand{\rolehead}[1]{\noindent\textbf{#1}\par}
\newcommand{\rolemeta}[1]{\noindent\textit{\small #1}\par\vspace{2pt}}
"""


def render_resume_latex(
    *,
    full_name: str,
    contact_info: dict[str, Any],
    content: dict[str, Any],
    language: str = "en",
    email: str | None = None,
) -> str:
    """Returns a complete, compilable LaTeX document.

    Deliberately mirrors render_resume_pdf's signature and field order so
    the two exports of one CV cannot drift apart — including the email
    leading the contact line, which is what an ATS keys its record on.
    """
    labels = labels_for(language)
    babel = "spanish" if language == "es" else "english"

    contact_parts = [
        escape(email),
        escape(contact_info.get("phone")),
        _url(contact_info.get("linkedin") or ""),
        _url(contact_info.get("github") or ""),
        _url(contact_info.get("portfolio") or ""),
        escape(contact_info.get("city")),
        escape(contact_info.get("country")),
    ]
    # `\quad\textbar\quad`, not `$|$`. Text extraction infers spaces from the
    # gap between glyphs, and a math-mode bar swallows the space before it:
    # measured on this document, the contact line came back as
    # "...829-619-8930| www.linkedin.com/..." with no separator space, so a
    # parser grabbing the URL as \S+ takes the bar along with it. Wide text
    # -mode quads leave a gap no extractor misses.
    contact_line = " \\quad\\textbar\\quad ".join(p for p in contact_parts if p)

    # Name, then the headline when there is one (only the master CV sets it),
    # then contact. Joined rather than written out so a CV without a headline
    # produces exactly the header it always did.
    header_lines = [f"{{\\LARGE\\bfseries {escape(full_name) or escape(labels['candidate'])}}}"]
    headline = content.get("headline")
    if headline:
        header_lines.append(f"{{\\large {escape(headline)}}}")
    header_lines.append(f"{{\\small {contact_line}}}")
    body: list[str] = ["\\begin{center}\n" + "\\\\[4pt]\n".join(header_lines) + "\n\\end{center}\n"]

    summary = content.get("summary")
    if summary:
        body.append(_section(labels["summary"], f"\\noindent {escape(summary)}"))

    skills = [s for s in (content.get("skills") or []) if s]
    if skills:
        body.append(_section(labels["skills"], "\\noindent " + ", ".join(escape(s) for s in skills)))

    experience = content.get("experience") or []
    if experience:
        body.append(_section(labels["experience"], _experience_block(experience, labels)))

    education = content.get("education") or []
    if education:
        body.append(_section(labels["education"], _education_block(education, labels)))

    # Certifications and spoken languages: only the master CV carries them,
    # and each section appears only when it has entries, so a tailored CV is
    # unaffected.
    certifications = [
        cert for cert in (content.get("certifications") or []) if isinstance(cert, dict) and cert.get("name")
    ]
    if certifications:
        cert_lines = []
        for cert in certifications:
            line = " --- ".join(escape(p) for p in (cert.get("name"), cert.get("issuer")) if p)
            if cert.get("date"):
                line = f"{line} ({escape(cert['date'])})"
            cert_lines.append(f"\\noindent {line}\\par")
        body.append(_section(labels["certifications"], "\n".join(cert_lines)))

    languages = [
        entry for entry in (content.get("languages") or []) if isinstance(entry, dict) and entry.get("name")
    ]
    if languages:
        spoken = ", ".join(
            " --- ".join(escape(p) for p in (entry.get("name"), entry.get("level")) if p)
            for entry in languages
        )
        body.append(_section(labels["languages"], f"\\noindent {spoken}"))

    preamble = PREAMBLE.replace("LANGUAGE_OPTION", babel)
    return (
        preamble
        + "\n\\begin{document}\n\n"
        + "\n".join(body)
        + "\n\\end{document}\n"
    )
