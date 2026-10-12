"""Llena el formulario real de Greenhouse con un borrador, SIN ENVIAR, y saca
una captura de pantalla.

Corre en su propio contenedor (backend/Dockerfile.agent), por eso no importa
nada de app/: recibe el borrador como JSON (Draft.to_dict(), o una entrada de
bench.json) y devuelve un informe por campo.

    python filler.py --draft draft.json --resume cv.pdf --out captura.png \\
        [--report informe.json] [--safe] [--country "Dominican Republic"]

Lo que se comprobo en vivo en job-boards.greenhouse.io (2026-10-12):
  * Cada campo tiene como id el nombre que da la API (first_name, resume,
    question_123). Los de seleccion multiple llegan como "question_123[]" y
    su id es sin los corchetes.
  * Los desplegables son comboboxes de React: se escribe la opcion y se elige
    en la lista que aparece.
  * Greenhouse pinta un campo "Country" obligatorio junto al telefono que NO
    viene en la API. Se llena con --country.
  * Hay un reCAPTCHA Enterprise invisible que se dispara al enviar. Por eso el
    envio (fase 3) tiene que contar con pasarle el control al usuario.

Lo que NUNCA hace: pulsar "Submit application", ni ningun boton de enviar. Y
por si acaso, aborta cualquier POST de envio antes de que salga del navegador.

--safe escribe datos ficticios en vez de los del usuario y sube un PDF de
prueba: un formulario de terceros puede registrar lo que se teclea aunque no
se envie, y el banco de prueba solo necesita comprobar que cada campo se
puede llenar.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

SAFE_IDENTITY = {
    "first_name": "Prueba",
    "last_name": "JobPilot",
    "preferred_name": "Prueba",
    "email": "prueba.jobpilot@example.com",
    "phone": "8095550100",
    "location": "Santo Domingo",
}

#: Campos cuyo id en la pagina no es el nombre que da la API. La ubicacion es
#: un autocompletado: se escribe la ciudad y se elige la primera sugerencia.
_ELEMENT_IDS = {"location": "candidate-location"}
SAFE_TEXT = "Respuesta de prueba de JobPilot (no enviar)"

#: Un PDF minimo valido, para --safe o si no se pasa --resume.
_DUMMY_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n164\n%%EOF\n"
)

_SUBMIT = re.compile(r"submit|send|enviar|apply now", re.I)
#: Envios de candidatura de Greenhouse. Se abortan aunque nada deberia
#: provocarlos: la segunda red de seguridad, despues de no pulsar el boton.
_SUBMIT_POST = re.compile(r"/applications?(\b|/)|/submit|/apply\b", re.I)


def _element_id(key: str) -> str:
    if key in _ELEMENT_IDS:
        return _ELEMENT_IDS[key]
    return key[:-2] if key.endswith("[]") else key


def _fill_autocomplete(page, element_id: str, text: str, timeout: int) -> None:
    campo = page.locator(_css_id(element_id))
    campo.click(timeout=timeout)
    campo.fill(text, timeout=timeout)
    try:
        page.locator("[role=option]").first.click(timeout=timeout)
    except Exception:  # noqa: BLE001 - sin sugerencias se queda el texto escrito
        pass


def _css_id(element_id: str) -> str:
    # Los ids de Greenhouse son seguros (letras, digitos, _), pero por si acaso.
    return "#" + re.sub(r"([^A-Za-z0-9_-])", r"\\\1", element_id)


def _pick_option(page, element_id: str, label: str, timeout: int) -> None:
    combo = page.locator(_css_id(element_id))
    combo.click(timeout=timeout)
    combo.fill(label, timeout=timeout)
    opcion = page.get_by_role("option", name=label, exact=True)
    if opcion.count() == 0:
        # Algunas opciones largas no exponen el nombre accesible completo.
        opcion = page.locator("[role=option]", has_text=label)
    opcion.first.click(timeout=timeout)


def _value_for(field: dict[str, Any], safe: bool) -> Any:
    if not safe:
        return field.get("value")
    if field["kind"] == "identity":
        return SAFE_IDENTITY.get(field["key"], "https://example.com/prueba")
    if field["type"] in ("text", "textarea"):
        return SAFE_TEXT
    return field.get("value")


def fill(draft: dict[str, Any], resume: Path, out: Path, *, safe: bool, country: str, timeout: int = 8000) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    url = draft.get("form_url") or draft["url"]
    informe: dict[str, Any] = {
        "url": url,
        "filled": [],
        "failed": [],
        "untouched": [],
        "blocked_posts": [],
        "captcha_iframe": False,
    }
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900}, locale="en-US")

        def _guard(route):
            if route.request.method == "POST" and _SUBMIT_POST.search(route.request.url):
                informe["blocked_posts"].append(route.request.url)
                return route.abort()
            return route.continue_()

        page.route("**/*", _guard)
        page.goto(url, wait_until="networkidle", timeout=60000)

        for field in draft["fields"]:
            if field["status"] != "filled":
                informe["untouched"].append(field["key"])
                continue
            element_id = _element_id(field["key"])
            try:
                if page.locator(_css_id(element_id)).count() == 0:
                    raise LookupError("no está en la página")
                if field["type"] == "file":
                    page.set_input_files(_css_id(element_id), str(resume), timeout=timeout)
                elif field["key"] in _ELEMENT_IDS:
                    _fill_autocomplete(page, element_id, str(_value_for(field, safe)), timeout)
                elif field["type"] in ("text", "textarea"):
                    page.fill(_css_id(element_id), str(_value_for(field, safe)), timeout=timeout)
                elif field["type"] == "select":
                    _pick_option(page, element_id, field["display"], timeout)
                elif field["type"] == "multiselect":
                    for etiqueta in [e.strip() for e in str(field["display"]).split(",") if e.strip()]:
                        _pick_option(page, element_id, etiqueta, timeout)
                informe["filled"].append(field["key"])
            except Exception as exc:  # noqa: BLE001 - un campo que falla no detiene los demas
                informe["failed"].append({"key": field["key"], "label": field["label"][:80], "error": str(exc)[:200]})

        # El "Country" que Greenhouse anade junto al telefono y la API no trae.
        if country and page.locator("#country").count() and not page.locator("#country").input_value():
            try:
                _pick_option(page, "country", country, timeout)
                informe["filled"].append("country (página)")
            except Exception as exc:  # noqa: BLE001
                informe["failed"].append({"key": "country (página)", "label": "Country", "error": str(exc)[:200]})

        informe["captcha_iframe"] = page.locator("iframe[src*='recaptcha'], iframe[src*='hcaptcha']").count() > 0
        informe["submit_buttons_seen"] = [t for t in page.locator("button").all_inner_texts() if _SUBMIT.search(t or "")]
        page.screenshot(path=str(out), full_page=True)
        informe["screenshot"] = str(out)
        browser.close()
    return informe


def main() -> None:
    parser = argparse.ArgumentParser(description="Llena un formulario de Greenhouse sin enviarlo.")
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--safe", action="store_true")
    parser.add_argument("--country", default="")
    args = parser.parse_args()

    datos = json.loads(args.draft.read_text(encoding="utf-8"))
    draft = datos.get("draft", datos)

    resume = args.resume
    if args.safe or resume is None:
        resume = Path(tempfile.gettempdir()) / "cv-prueba-jobpilot.pdf"
        resume.write_bytes(_DUMMY_PDF)

    informe = fill(draft, resume, args.out, safe=args.safe, country=args.country)
    texto = json.dumps(informe, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(texto, encoding="utf-8")
    print(texto)
    sys.exit(0 if not informe["failed"] else 2)


if __name__ == "__main__":
    main()
