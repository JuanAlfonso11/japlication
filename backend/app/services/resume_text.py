"""Plain-text rendering of a CV — a tailored resume_versions row or the master CV.

The twin of resume_pdf.py and resume_latex.py. Section headers come from the
same profile_i18n.CV_LABELS table, so the exports of one CV cannot end up in
different languages. It lives here rather than inside the resumes router so
the master CV export in the profile router renders through the same code.
"""

from __future__ import annotations

from typing import Any

from app.services.profile_i18n import labels_for


def _text(value: Any) -> str:
    return str(value or "").strip()


def render_resume_text(*, title: str, content: dict[str, Any], language: str | None) -> str:
    """`headline`, `certifications` and `languages` are optional and printed
    only when present — only the master CV sets them."""
    labels = labels_for(language)
    lines: list[str] = [title, "=" * len(title)]
    if _text(content.get("headline")):
        lines.append(_text(content["headline"]))
    lines.append("")

    summary = _text(content.get("summary"))
    if summary:
        lines += [labels["summary"], summary, ""]

    skills = [_text(s) for s in (content.get("skills") or []) if _text(s)]
    if skills:
        lines += [labels["skills"], ", ".join(skills), ""]

    experience = [e for e in (content.get("experience") or []) if isinstance(e, dict)]
    if experience:
        lines.append(labels["experience"])
        for exp in experience:
            header = " — ".join(_text(p) for p in (exp.get("title"), exp.get("company")) if _text(p))
            end = exp.get("end_date") or labels["present"]
            span = " – ".join(_text(p) for p in (exp.get("start_date"), end) if _text(p))
            lines.append(f"{header} ({span})" if header else f"({span})")
            if _text(exp.get("location")):
                lines.append(_text(exp["location"]))
            for bullet in exp.get("bullets") or []:
                if _text(bullet):
                    lines.append(f"- {_text(bullet)}")
            lines.append("")

    education = [e for e in (content.get("education") or []) if isinstance(e, dict)]
    if education:
        lines.append(labels["education"])
        for edu in education:
            degree = _text(edu.get("degree"))
            field = _text(edu.get("field"))
            # The same rule the PDF and LaTeX exports already apply, which
            # this one had missed: "Bachelor's Degree in Computer Science
            # Engineering" with field "Computer Science" came out as
            # "...Engineering in Computer Science".
            parts = [degree] if field and field.lower() in degree.lower() else [degree, field]
            deg = labels["degree_join"].join(p for p in parts if p)
            line = " — ".join(p for p in (deg, _text(edu.get("institution"))) if p)
            end = edu.get("end_date") or (labels["present"] if edu.get("start_date") else None)
            span = " – ".join(_text(p) for p in (edu.get("start_date"), end) if _text(p))
            lines.append(f"{line} ({span})" if span else line)
        lines.append("")

    certifications = [
        c for c in (content.get("certifications") or []) if isinstance(c, dict) and _text(c.get("name"))
    ]
    if certifications:
        lines.append(labels["certifications"])
        for cert in certifications:
            line = " — ".join(_text(p) for p in (cert.get("name"), cert.get("issuer")) if _text(p))
            lines.append(f"{line} ({_text(cert['date'])})" if _text(cert.get("date")) else line)
        lines.append("")

    languages = [
        entry for entry in (content.get("languages") or []) if isinstance(entry, dict) and _text(entry.get("name"))
    ]
    if languages:
        spoken = ", ".join(
            " — ".join(_text(p) for p in (entry.get("name"), entry.get("level")) if _text(p))
            for entry in languages
        )
        lines += [labels["languages"], spoken, ""]

    return "\n".join(lines).strip() + "\n"
