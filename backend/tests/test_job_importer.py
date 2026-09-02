import pytest
from fastapi import HTTPException

from app.services.job_importer import parse_job_html

JSONLD_JOB_HTML = """
<!DOCTYPE html>
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "JobPosting",
  "title": "Senior Backend Engineer",
  "description": "<p>We are looking for a Senior Backend Engineer to join our team.</p><h3>Requirements</h3><ul><li>5+ years of experience with Python</li><li>Experience with PostgreSQL and AWS</li></ul><h3>Responsibilities</h3><ul><li>Design REST APIs</li><li>Mentor junior engineers</li></ul><h3>Nice to have</h3><ul><li>Experience with Kubernetes</li></ul>",
  "datePosted": "2024-03-01",
  "employmentType": "FULL_TIME",
  "hiringOrganization": {
    "@type": "Organization",
    "name": "Acme Corp"
  },
  "jobLocation": {
    "@type": "Place",
    "address": {
      "@type": "PostalAddress",
      "addressLocality": "Remote",
      "addressCountry": "US"
    }
  },
  "baseSalary": {
    "@type": "MonetaryAmount",
    "currency": "USD",
    "value": {
      "@type": "QuantitativeValue",
      "minValue": 120000,
      "maxValue": 160000
    }
  }
}
</script>
<title>Senior Backend Engineer at Acme Corp</title>
</head>
<body>
<h1>Senior Backend Engineer</h1>
<p>Some visible page content that duplicates the JSON-LD description.</p>
</body>
</html>
"""

PLAIN_HTML_NO_JSONLD = """
<!DOCTYPE html>
<html>
<head><title>Backend Developer - Widgets Inc</title></head>
<body>
<h1>Backend Developer</h1>
<p>Widgets Inc is hiring a Backend Developer to join our growing platform team.</p>
<h3>Requirements</h3>
<ul>
  <li>3+ years of experience with Python</li>
  <li>Solid knowledge of SQL and REST APIs</li>
  <li>Experience with Docker</li>
</ul>
<h3>Responsibilities</h3>
<ul>
  <li>Build and maintain backend services</li>
  <li>Collaborate with the frontend team</li>
</ul>
<h3>Nice to have</h3>
<ul>
  <li>Experience with Kubernetes</li>
</ul>
<p>This is a remote, full-time position.</p>
</body>
</html>
"""


class TestJsonLdParsing:
    def test_extracts_core_fields_from_jsonld(self):
        result = parse_job_html(JSONLD_JOB_HTML, url="https://example.com/jobs/123")
        assert result["title"] == "Senior Backend Engineer"
        assert result["company"] == "Acme Corp"
        assert result["employment_type"] == "full_time"
        assert result["salary_min"] == 120000
        assert result["salary_max"] == 160000
        assert result["salary_currency"] == "USD"
        assert result["posted_at"] is not None
        assert result["source_url"] == "https://example.com/jobs/123"
        assert "Remote" in (result["location"] or "")

    def test_extracts_requirements_and_responsibilities(self):
        result = parse_job_html(JSONLD_JOB_HTML)
        assert any("Python" in r for r in result["requirements"])
        assert any("REST APIs" in r or "Design" in r for r in result["responsibilities"])

    def test_extracts_skills_split_required_vs_nice_to_have(self):
        result = parse_job_html(JSONLD_JOB_HTML)
        skill_names = {s["name"]: s["importance"] for s in result["skills_required"]}
        assert skill_names.get("Python") == "required"
        assert skill_names.get("PostgreSQL") == "required"
        assert skill_names.get("AWS") == "required"
        assert skill_names.get("Kubernetes") == "nice_to_have"

    def test_raw_html_preserved(self):
        result = parse_job_html(JSONLD_JOB_HTML, url="https://example.com/jobs/123")
        assert result["raw_html"] == JSONLD_JOB_HTML


class TestHeuristicFallbackParsing:
    def test_parses_without_jsonld(self):
        result = parse_job_html(PLAIN_HTML_NO_JSONLD, url="https://example.com/jobs/456")
        assert "Backend Developer" in result["title"]
        assert result["description"]
        assert result["source_url"] == "https://example.com/jobs/456"

    def test_extracts_requirements_section(self):
        result = parse_job_html(PLAIN_HTML_NO_JSONLD)
        assert any("Python" in r for r in result["requirements"])
        assert any("Docker" in r for r in result["requirements"])

    def test_extracts_responsibilities_section(self):
        result = parse_job_html(PLAIN_HTML_NO_JSONLD)
        assert any("backend services" in r.lower() for r in result["responsibilities"])

    def test_extracts_skills_and_remote_type(self):
        result = parse_job_html(PLAIN_HTML_NO_JSONLD)
        skill_names = {s["name"] for s in result["skills_required"]}
        assert "Python" in skill_names
        assert "SQL" in skill_names
        assert "REST APIs" in skill_names
        assert result["remote_type"] == "remote"
        assert result["employment_type"] == "full_time"

    def test_empty_html_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_job_html("<html><body></body></html>")
        assert exc_info.value.status_code == 422

    def test_garbage_input_does_not_crash_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            parse_job_html("")
        assert exc_info.value.status_code == 422
