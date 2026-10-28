"""El servicio del contenedor `agent`: recibe un borrador aprobado y lo envia.

    POST /submit  {"draft": {form_url, url, fields}, "country": "...",
                   "resume_pdf": "<base64>", "cover_letter_pdf": "<base64>|null"}
      -> {"outcome": "submitted" | "challenge" | "unconfirmed" | "invalid" | "error",
          "filled": [...], "failed": [...], "errors": [...], "detail": "..."}
    GET  /health  -> {"ok": true}

Solo lo llama el backend (servicio `backend` de docker compose), por la red
interna: el puerto no se publica en el host. Corre en su propio contenedor
(backend/Dockerfile.agent) porque Chromium pesa mas de 1 GB, y por eso no
importa nada de app/: solo filler.py, que va al lado.

Un envio a la vez, a proposito: el servidor no es concurrente, asi que dos
aprobaciones seguidas salen una detras de otra y nunca compiten por la misma
pagina.

Reglas que este archivo hace cumplir, ademas de las de filler.py:
  * Solo formularios de Greenhouse (*.greenhouse.io). Cualquier otra URL se
    rechaza: el backend no deberia mandarla nunca, y si lo hiciera, este
    servicio no navega a donde le digan.
  * Nunca en modo --safe (datos ficticios) y nunca con un CV vacio.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:  # dentro del contenedor, filler.py esta al lado
    import filler  # type: ignore
except ImportError:  # pragma: no cover - desde el repo
    from app.services.apply_agent import filler  # type: ignore

logger = logging.getLogger("jobpilot.agent")

MAX_BODY = 12 * 1024 * 1024
_ALLOWED_HOST_SUFFIX = ".greenhouse.io"


class BadRequest(ValueError):
    pass


def _greenhouse_url(url: Any) -> str:
    if not isinstance(url, str):
        raise BadRequest("Falta la URL del formulario.")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "greenhouse.io" or host.endswith(_ALLOWED_HOST_SUFFIX)):
        raise BadRequest("Solo se envían formularios de Greenhouse.")
    return url


def _pdf(b64: Any, nombre: str, carpeta: Path) -> Path:
    try:
        datos = base64.b64decode(b64 or "", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BadRequest(f"{nombre}: no es base64 válido.") from exc
    if not datos.startswith(b"%PDF"):
        raise BadRequest(f"{nombre}: no es un PDF.")
    ruta = carpeta / f"{nombre}.pdf"
    ruta.write_bytes(datos)
    return ruta


def handle_submit(body: dict[str, Any]) -> dict[str, Any]:
    draft = body.get("draft") or {}
    url = _greenhouse_url(draft.get("form_url") or draft.get("url"))
    campos = draft.get("fields")
    if not isinstance(campos, list) or not campos:
        raise BadRequest("El borrador no trae campos.")
    with tempfile.TemporaryDirectory(prefix="jobpilot-agent-") as tmp:
        carpeta = Path(tmp)
        cv = _pdf(body.get("resume_pdf"), "CV", carpeta)
        carta = _pdf(body["cover_letter_pdf"], "Carta", carpeta) if body.get("cover_letter_pdf") else None
        captura = carpeta / "captura.png"
        informe = filler.fill(
            {"form_url": url, "url": url, "fields": campos},
            cv,
            captura,
            safe=False,
            country=str(body.get("country") or ""),
            submit=True,
            cover_letter=carta,
        )
        if captura.exists():
            informe["screenshot_b64"] = base64.b64encode(captura.read_bytes()).decode("ascii")
        informe.pop("screenshot", None)
    if not informe.get("outcome"):
        informe["outcome"] = "error"
    return informe


class Handler(BaseHTTPRequestHandler):
    server_version = "JobPilotAgent/1"

    def _json(self, status: int, data: dict[str, Any]) -> None:
        cuerpo = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"ok": True})
        else:
            self._json(404, {"detail": "No existe."})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/submit":
            self._json(404, {"detail": "No existe."})
            return
        largo = int(self.headers.get("Content-Length") or 0)
        if largo <= 0 or largo > MAX_BODY:
            self._json(413, {"detail": "Cuerpo vacío o demasiado grande."})
            return
        try:
            body = json.loads(self.rfile.read(largo))
            self._json(200, handle_submit(body))
        except BadRequest as exc:
            self._json(400, {"outcome": "error", "detail": str(exc)})
        except Exception as exc:  # noqa: BLE001 - el backend pasa el control al usuario
            logger.exception("Fallo al enviar")
            self._json(200, {"outcome": "error", "detail": str(exc)[:300]})

    def log_message(self, fmt: str, *args: Any) -> None:  # sin datos personales en el log
        logger.info("%s %s", self.command, self.path)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    puerto = int(os.environ.get("AGENT_PORT", "8800"))
    logger.info("Agente de envío escuchando en :%d", puerto)
    HTTPServer(("0.0.0.0", puerto), Handler).serve_forever()


if __name__ == "__main__":
    main()
