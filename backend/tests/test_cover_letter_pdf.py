from app.services.cover_letter_pdf import render_cover_letter_pdf

CONTENT = "Dear Hiring Team,\n\nI'm writing to express my interest.\n\nSincerely,\nJuan Alvarado"
CONTACT_INFO = {"city": "Santiago", "country": "Dominican Republic", "phone": "809-555-0000"}


def test_render_cover_letter_pdf_returns_valid_pdf_bytes():
    pdf_bytes = render_cover_letter_pdf(full_name="Juan Alvarado", contact_info=CONTACT_INFO, content=CONTENT)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 400


def test_render_cover_letter_pdf_handles_missing_fields():
    pdf_bytes = render_cover_letter_pdf(full_name="", contact_info={}, content="")
    assert pdf_bytes.startswith(b"%PDF")


def test_render_cover_letter_pdf_escapes_special_characters():
    pdf_bytes = render_cover_letter_pdf(
        full_name="A & B", contact_info={}, content="Worked with <script> & other things"
    )
    assert pdf_bytes.startswith(b"%PDF")
