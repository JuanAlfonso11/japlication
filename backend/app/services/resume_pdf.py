"""Renders a resume_versions row as a real, ATS-safe PDF.

"ATS-safe" here means something specific and achievable: single-column,
standard section headers ("EXPERIENCE"/"EDUCATION"/"SKILLS"), real
selectable text built with reportlab's Paragraph flowables (never an
image, table, or text box) — the layout choices that let the resume-parser
almost every modern application form ships (Greenhouse, Lever, Workday,
LinkedIn/Indeed Easy Apply) actually read the file correctly and
autofill name/contact/experience from it. That's a real, well-documented
technical problem (multi-column layouts, graphics, and non-standard
headers are the classic causes of an ATS mangling or dropping a resume
before a human ever sees it) and this eliminates it.

What this can NOT do: guarantee a human recruiter — or a keyword-matching
screen — decides you're a fit. No formatting choice can promise that; it
depends on the job, the applicant pool, and how well the content (already
handled by resume_adapter.py's tailoring) matches what's being asked for.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_NAME_STYLE = ParagraphStyle("Name", fontName="Helvetica-Bold", fontSize=16, leading=19, alignment=TA_LEFT)
_CONTACT_STYLE = ParagraphStyle(
    "Contact", fontName="Helvetica", fontSize=9.5, leading=12, spaceAfter=10, textColor="#333333"
)
_SECTION_STYLE = ParagraphStyle(
    "Section", fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=12, spaceAfter=4, textColor="#111111"
)
_BODY_STYLE = ParagraphStyle("Body", fontName="Helvetica", fontSize=10, leading=13.5, spaceAfter=4)
_ROLE_STYLE = ParagraphStyle("Role", fontName="Helvetica-Bold", fontSize=10.5, leading=13, spaceBefore=6)
_MUTED_STYLE = ParagraphStyle("Muted", fontName="Helvetica-Oblique", fontSize=9.5, leading=12, spaceAfter=3, textColor="#555555")
_BULLET_STYLE = ParagraphStyle("Bullet", fontName="Helvetica", fontSize=10, leading=13.5, leftIndent=14, spaceAfter=2)


def _esc(value: Any) -> str:
    text = str(value or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _join(parts: list[Any], sep: str) -> str:
    return sep.join(_esc(p) for p in parts if p)


def render_resume_pdf(*, full_name: str, contact_info: dict[str, Any], content: dict[str, Any]) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        title=full_name or "Resume",
    )

    story: list[Any] = [Paragraph(_esc(full_name) or "Candidate", _NAME_STYLE)]

    contact_line = _join(
        [
            contact_info.get("city"),
            contact_info.get("country"),
            contact_info.get("phone"),
            contact_info.get("linkedin"),
            contact_info.get("github"),
            contact_info.get("portfolio"),
        ],
        "  |  ",
    )
    story.append(Paragraph(contact_line, _CONTACT_STYLE) if contact_line else Spacer(1, 8))

    summary = content.get("summary")
    if summary:
        story.append(Paragraph("SUMMARY", _SECTION_STYLE))
        story.append(Paragraph(_esc(summary), _BODY_STYLE))

    skills = [s for s in (content.get("skills") or []) if s]
    if skills:
        story.append(Paragraph("SKILLS", _SECTION_STYLE))
        story.append(Paragraph(_join(skills, ", "), _BODY_STYLE))

    experience = content.get("experience") or []
    if experience:
        story.append(Paragraph("EXPERIENCE", _SECTION_STYLE))
        for entry in experience:
            if not isinstance(entry, dict):
                continue
            header = _join([entry.get("title"), entry.get("company")], " — ")
            story.append(Paragraph(header or "Role", _ROLE_STYLE))
            dates = _join([entry.get("start_date"), entry.get("end_date") or "Present"], " – ")
            meta = _join([dates, entry.get("location")], "  |  ")
            if meta:
                story.append(Paragraph(meta, _MUTED_STYLE))
            for bullet in entry.get("bullets") or []:
                if bullet:
                    story.append(Paragraph(f"• {_esc(bullet)}", _BULLET_STYLE))

    education = content.get("education") or []
    if education:
        story.append(Paragraph("EDUCATION", _SECTION_STYLE))
        for entry in education:
            if not isinstance(entry, dict):
                continue
            degree_field = _join([entry.get("degree"), entry.get("field")], ", ")
            line = _join([degree_field, entry.get("institution")], " — ")
            dates = _join([entry.get("start_date"), entry.get("end_date")], " – ")
            if dates:
                line = f"{line} ({dates})"
            if line:
                story.append(Paragraph(line, _BODY_STYLE))

    doc.build(story)
    return buffer.getvalue()
