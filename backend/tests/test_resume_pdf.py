from app.services.resume_pdf import render_resume_pdf

CONTENT = {
    "summary": "Backend developer with API and database experience.",
    "skills": ["C#", "PostgreSQL", "Docker"],
    "experience": [
        {
            "company": "Acme",
            "title": "Backend Developer",
            "start_date": "2022-01",
            "end_date": None,
            "location": "Remote",
            "bullets": ["Built REST APIs", "Maintained CI/CD pipelines"],
        }
    ],
    "education": [
        {"institution": "PUCMM", "degree": "Ingenieria", "field": "Software", "start_date": "2018", "end_date": "2022"}
    ],
}

CONTACT_INFO = {"city": "Santiago", "country": "Dominican Republic", "phone": "809-555-0000"}


def test_render_resume_pdf_returns_valid_pdf_bytes():
    pdf_bytes = render_resume_pdf(full_name="Juan Alvarado", contact_info=CONTACT_INFO, content=CONTENT)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 500


def test_render_resume_pdf_handles_missing_optional_fields():
    pdf_bytes = render_resume_pdf(full_name="", contact_info={}, content={})
    assert pdf_bytes.startswith(b"%PDF")


def test_render_resume_pdf_escapes_special_characters():
    content = {"summary": "Worked with <script>alert(1)</script> & other things", "skills": [], "experience": [], "education": []}
    pdf_bytes = render_resume_pdf(full_name="A & B", contact_info={}, content=content)
    assert pdf_bytes.startswith(b"%PDF")
