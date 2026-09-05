"""Renders a cover_letters row as a simple, clean PDF — same rationale as
resume_pdf.py (single column, real selectable text, no tables/images) so
it uploads cleanly to any application form that accepts a separate cover
letter file alongside the resume.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_NAME_STYLE = ParagraphStyle("Name", fontName="Helvetica-Bold", fontSize=13, leading=16)
_CONTACT_STYLE = ParagraphStyle(
    "Contact", fontName="Helvetica", fontSize=9.5, leading=12, spaceAfter=18, textColor="#333333"
)
_BODY_STYLE = ParagraphStyle("Body", fontName="Helvetica", fontSize=10.5, leading=16, spaceAfter=12)


def _esc(value: Any) -> str:
    text = str(value or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_cover_letter_pdf(*, full_name: str, contact_info: dict[str, Any], content: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=0.85 * inch,
        rightMargin=0.85 * inch,
        title=full_name or "Cover Letter",
    )

    story: list[Any] = [Paragraph(_esc(full_name) or "Candidate", _NAME_STYLE)]

    contact_line = "  |  ".join(
        _esc(p)
        for p in [
            contact_info.get("city"),
            contact_info.get("country"),
            contact_info.get("phone"),
            contact_info.get("linkedin"),
        ]
        if p
    )
    story.append(Paragraph(contact_line, _CONTACT_STYLE) if contact_line else Spacer(1, 14))

    for paragraph in (content or "").split("\n\n"):
        cleaned = paragraph.strip()
        if not cleaned:
            continue
        # Preserve single newlines within a paragraph (e.g. a signature
        # block: "Sincerely,\nJuan Alvarado") as real line breaks.
        story.append(Paragraph(_esc(cleaned).replace("\n", "<br/>"), _BODY_STYLE))

    doc.build(story)
    return buffer.getvalue()
