"""Lo que encontró la prueba de estrés con una cuenta nueva (sin CV)."""

from types import SimpleNamespace

import pytest

from app.services import match_engine
from app.services.anthropic_client import TruncatedResponse, response_text
from app.services.job_importer import JobImportError, parse_job_html, strip_markup


@pytest.mark.asyncio
async def test_job_added_before_the_cv_is_scored_when_the_profile_is_saved(async_client, user_and_headers):
    """Agregar sin CV guardaba la vacante sin puntaje, y la cola de Inicio solo
    lista vacantes con puntaje: quedaba invisible para siempre."""
    _user, headers = user_and_headers
    job = await async_client.post(
        "/jobs",
        json={"title": "Ingeniero de Mantenimiento", "company": "Acme", "description": "Mantenimiento preventivo TPM."},
        headers=headers,
    )
    assert job.status_code == 201, job.text
    assert job.json()["match"] is None
    assert (await async_client.get("/matches", headers=headers)).json()["total"] == 0

    saved = await async_client.put(
        "/profile",
        json={"headline": "Ingeniera de mantenimiento", "skills": [{"name": "TPM"}]},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text

    queue = (await async_client.get("/matches", headers=headers)).json()
    assert [j["id"] for j in queue["items"]] == [job.json()["id"]]


def test_a_page_that_is_not_a_job_posting_is_rejected():
    html = "<html><title>Google</title><body>Google Imágenes Más Acceder Preferencias Ayuda</body></html>"
    with pytest.raises(JobImportError, match="no parece una vacante"):
        parse_job_html(html, "https://www.google.com")


def test_escaped_html_descriptions_come_out_as_text():
    assert strip_markup("<div class='x'><p>Hola</p></div>") == "Hola"
    assert strip_markup("Texto normal con a < b") == "Texto normal con a < b"


def test_a_reply_cut_by_max_tokens_says_so():
    cut = SimpleNamespace(stop_reason="max_tokens", content=[SimpleNamespace(type="text", text='{"a": "')])
    with pytest.raises(TruncatedResponse):
        response_text(cut)


def test_batch_scores_come_from_one_call_and_fail_closed(monkeypatch):
    calls = []

    def reply(text):
        class Client:
            class messages:
                @staticmethod
                def create(**kwargs):
                    calls.append(kwargs)
                    return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])

        return Client()

    reply_text = "```json\n[55, 120, -3]\n```\nNota: el segundo encaja mejor."
    monkeypatch.setattr(match_engine, "get_anthropic_client", lambda: reply(reply_text))
    assert match_engine.batch_semantic_scores("perfil", ["a", "b", "c"]) == [55.0, 100.0, 0.0]
    assert len(calls) == 1

    # Wrong count: no guessing which score belongs to which job.
    monkeypatch.setattr(match_engine, "get_anthropic_client", lambda: reply("[55]"))
    assert match_engine.batch_semantic_scores("perfil", ["a", "b"]) == [None, None]
