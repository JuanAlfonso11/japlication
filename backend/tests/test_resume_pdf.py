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


def _text_of(pdf: bytes) -> str:
    from io import BytesIO

    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        from PyPDF2 import PdfReader

    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)


class TestAtsContactBlock:
    """What a resume parser has to be able to pull off the top of the page.

    Every ATS keys its candidate record on the email address, and several use
    it as the dedup key. A resume with no findable email produces a record
    nobody can reply to — which is a worse outcome than a badly worded
    bullet, and it is invisible to the person who sent it.
    """

    CONTENT = {
        "summary": "Engineer.",
        "skills": ["C#"],
        "experience": [],
        "education": [],
    }

    def test_email_is_rendered(self):
        from app.services.resume_pdf import render_resume_pdf

        pdf = render_resume_pdf(
            full_name="Juan Alvarado",
            contact_info={"phone": "+1 829-619-8930", "city": "Santiago"},
            content=self.CONTENT,
            email="juan@example.com",
        )
        assert "juan@example.com" in _text_of(pdf)

    def test_tracking_parameters_are_stripped_from_contact_links(self):
        """A LinkedIn URL copied from the mobile app carries ~60 characters
        of share tracking, which pushes it past the line width — and a
        parser reading the wrapped text gets a broken link."""
        from app.services.resume_pdf import render_resume_pdf

        pdf = render_resume_pdf(
            full_name="Juan Alvarado",
            contact_info={
                "linkedin": "https://www.linkedin.com/in/juan-a5a995231"
                "?utm_source=share_via&utm_content=profile&utm_medium=member_android",
                "github": "https://github.com/juan?tab=repositories",
            },
            content=self.CONTENT,
            email="juan@example.com",
        )
        text = _text_of(pdf)
        assert "utm_source" not in text
        assert "tab=repositories" not in text
        assert "linkedin.com/in/juan-a5a995231" in text.replace("\n", "")

    def test_degree_does_not_repeat_the_field_it_already_names(self):
        from app.services.resume_pdf import render_resume_pdf

        pdf = render_resume_pdf(
            full_name="Juan Alvarado",
            contact_info={},
            content={
                **self.CONTENT,
                "education": [
                    {
                        "institution": "PUCMM",
                        "degree": "Bachelor's Degree in Computer Science Engineering",
                        "field": "Computer Science",
                        "start_date": "2020",
                        "end_date": None,
                    }
                ],
            },
            email="juan@example.com",
        )
        text = _text_of(pdf).replace("\n", " ")
        assert "Engineering, Computer Science" not in text
        assert "Bachelor's Degree in Computer Science Engineering" in text
