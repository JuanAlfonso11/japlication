"""El navegador del agente contra un formulario falso, servido en local.

Imita lo que importa de Greenhouse: ids por nombre de campo, un combobox de
React, los dos archivos (CV y carta) y el boton "Submit application". El
modo de la URL decide que pasa al enviar: confirmacion, desafio de CAPTCHA,
errores de validacion o nada.

Nunca toca un formulario real. Necesita Playwright con Chromium, que solo
esta en el contenedor `agent`: en la suite normal del backend se salta.
Para correrlo fuera:  python -m pytest --noconftest tests/test_agent_submit.py
"""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from app.services.apply_agent import agent_server, filler  # noqa: E402

PAGE = """<!doctype html><html><body>
<form id="f">
  <label for="first_name">First Name*</label><input id="first_name" name="first_name" required>
  <label for="last_name">Last Name*</label><input id="last_name" name="last_name" required>
  <label for="email">Email*</label><input id="email" name="email" required>
  <label for="resume">Resume*</label><input type="file" id="resume" required>
  <label for="cover_letter">Cover letter</label><input type="file" id="cover_letter">
  <label for="question_1">Do you require sponsorship?*</label>
  <input id="question_1" role="combobox" autocomplete="off">
  <div id="opts" hidden>
    <div role="option" data-v="1">Yes</div><div role="option" data-v="0">No</div>
  </div>
  <label for="question_2">Consent*</label><input type="checkbox" id="question_2">
  <button type="submit">Submit application</button>
</form>
<div id="out"></div>
<script>
  const q = document.getElementById('question_1'), opts = document.getElementById('opts');
  q.addEventListener('click', () => opts.hidden = false);
  q.addEventListener('input', () => opts.hidden = false);
  opts.querySelectorAll('[role=option]').forEach(o => o.addEventListener('click', () => {
    q.value = o.textContent; q.dataset.v = o.dataset.v; opts.hidden = true;
  }));
  const mode = new URLSearchParams(location.search).get('mode');
  document.getElementById('f').addEventListener('submit', async (e) => {
    e.preventDefault();
    const files = [document.getElementById('resume').files[0]?.name || '',
                   document.getElementById('cover_letter').files[0]?.name || ''];
    await fetch('/applications', {method: 'POST', body: JSON.stringify({
      first: document.getElementById('first_name').value, sponsorship: q.value, files})});
    const out = document.getElementById('out');
    if (mode === 'ok') out.innerHTML = '<h1>Thank you for applying.</h1>';
    if (mode === 'challenge') out.innerHTML =
      '<iframe src="/recaptcha/api2/bframe?k=x" style="width:400px;height:580px"></iframe>';
    if (mode === 'invalid') out.innerHTML = '<p class="error">Please enter a valid phone number</p>';
  });
</script></body></html>"""


class _Server:
    def __init__(self) -> None:
        self.posts: list[dict] = []
        servidor = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                cuerpo = PAGE.encode() if self.path.startswith("/form") else b"<html><body>challenge</body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(cuerpo)

            def do_POST(self):  # noqa: N802
                largo = int(self.headers.get("Content-Length") or 0)
                servidor.posts.append(json.loads(self.rfile.read(largo) or b"{}"))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()


@pytest.fixture
def form_server():
    servidor = _Server()
    yield servidor
    servidor.close()


def _draft(url: str, consent_answered: bool = True) -> dict:
    campos = [
        {"key": "first_name", "label": "First Name", "type": "text", "required": True, "status": "filled", "value": "Juan"},
        {"key": "last_name", "label": "Last Name", "type": "text", "required": True, "status": "filled", "value": "Alvarado"},
        {"key": "email", "label": "Email", "type": "text", "required": True, "status": "filled", "value": "j@example.com"},
        {"key": "resume", "label": "Resume", "type": "file", "required": True, "status": "filled", "value": "tailored_cv"},
        {"key": "cover_letter", "label": "Cover letter", "type": "file", "required": False, "status": "filled",
         "value": "cover_letter"},
        {"key": "question_1", "label": "Do you require sponsorship?", "type": "select", "required": True,
         "status": "filled", "value": "0", "display": "No"},
    ]
    return {"form_url": url, "url": url, "fields": campos}


def _pdfs(tmp_path: Path) -> tuple[Path, Path]:
    cv, carta = tmp_path / "CV.pdf", tmp_path / "Carta.pdf"
    cv.write_bytes(filler._DUMMY_PDF)
    carta.write_bytes(filler._DUMMY_PDF)
    return cv, carta


def test_submits_once_and_sees_the_confirmation(form_server, tmp_path):
    cv, carta = _pdfs(tmp_path)
    informe = filler.fill(_draft(form_server.url + "/form?mode=ok"), cv, tmp_path / "s.png",
                          safe=False, country="", submit=True, cover_letter=carta, wait_seconds=10)
    assert informe["outcome"] == "submitted", informe
    assert len(form_server.posts) == 1
    enviado = form_server.posts[0]
    assert enviado["first"] == "Juan" and enviado["sponsorship"] == "No"
    # El CV en el campo del CV y la carta en el de la carta.
    assert enviado["files"] == ["CV.pdf", "Carta.pdf"]


def test_a_captcha_challenge_goes_back_to_the_user(form_server, tmp_path):
    cv, carta = _pdfs(tmp_path)
    informe = filler.fill(_draft(form_server.url + "/form?mode=challenge"), cv, tmp_path / "s.png",
                          safe=False, country="", submit=True, cover_letter=carta, wait_seconds=10)
    assert informe["outcome"] == "challenge"
    assert len(form_server.posts) == 1  # un solo clic: nunca se reintenta


def test_validation_errors_are_reported(form_server, tmp_path):
    cv, carta = _pdfs(tmp_path)
    informe = filler.fill(_draft(form_server.url + "/form?mode=invalid"), cv, tmp_path / "s.png",
                          safe=False, country="", submit=True, cover_letter=carta, wait_seconds=10)
    assert informe["outcome"] == "invalid"
    assert "Please enter a valid phone number" in informe["errors"]


def test_no_confirmation_is_unconfirmed_not_submitted(form_server, tmp_path):
    cv, carta = _pdfs(tmp_path)
    informe = filler.fill(_draft(form_server.url + "/form?mode=silent"), cv, tmp_path / "s.png",
                          safe=False, country="", submit=True, cover_letter=carta, wait_seconds=5)
    assert informe["outcome"] == "unconfirmed"


def test_a_required_field_that_cannot_be_filled_is_never_sent(form_server, tmp_path):
    cv, carta = _pdfs(tmp_path)
    draft = _draft(form_server.url + "/form?mode=ok")
    draft["fields"].append({"key": "question_9", "label": "Missing", "type": "text", "required": True,
                            "status": "filled", "value": "x"})
    informe = filler.fill(draft, cv, tmp_path / "s.png", safe=False, country="", submit=True,
                          cover_letter=carta, wait_seconds=5)
    assert informe["outcome"] == "error"
    assert form_server.posts == []


def test_fill_mode_never_submits(form_server, tmp_path):
    cv, _ = _pdfs(tmp_path)
    informe = filler.fill(_draft(form_server.url + "/form?mode=ok"), cv, tmp_path / "s.png",
                          safe=False, country="")
    assert informe["outcome"] is None
    assert form_server.posts == []


def test_server_only_sends_greenhouse_forms():
    pdf = base64.b64encode(filler._DUMMY_PDF).decode()
    for url in ("http://job-boards.greenhouse.io/a/jobs/1", "https://evil.example.com/greenhouse.io",
                "https://greenhouse.io.evil.com/x"):
        with pytest.raises(agent_server.BadRequest):
            agent_server.handle_submit({"draft": {"form_url": url, "fields": [{"key": "a"}]}, "resume_pdf": pdf})
    with pytest.raises(agent_server.BadRequest):
        agent_server.handle_submit({"draft": {"form_url": "https://job-boards.greenhouse.io/a/jobs/1",
                                              "fields": [{"key": "a"}]}, "resume_pdf": base64.b64encode(b"hola").decode()})
