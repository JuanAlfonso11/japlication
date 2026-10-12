# Agente de aplicación

Plan completo (arquitectura, modos de envío, riesgos y la pestaña Legal):
[JobPilot — Plan del agente de auto-aplicación](https://claude.ai/code/artifact/557c9f98-e500-4a6b-8bc8-82a8b04dcedb).
Este archivo lleva el estado en el repo.

El agente se construye desde cero, inspirado en el producto de Sorce, sin su
código: el de ellos corre en sus servidores y sus términos prohíben la
ingeniería inversa. Lee ofertas por APIs públicas de LECTURA y llena el
formulario público del empleador. Nunca usa las APIs de envío de los ATS (exigen
la clave del empleador, ver `app/services/apply_target.py`). Nunca evade un
CAPTCHA o un login.

## Fases

| Fase | Qué | Puerta | Estado |
|---|---|---|---|
| 1 | Ofertas de Greenhouse, Lever y Ashby y perfil con lo básico | Ofertas reales en el swipe y perfil confirmado | Ofertas: hecho (`ats_boards.py`). Perfil: falta completar respuestas guardadas (ver abajo) |
| 2 | Borradores para Greenhouse, sin enviar | 90 % de campos correctos en 20 formularios | Borradores y llenado con navegador hechos; falta que el usuario califique `bench.md` |
| 3 | Revisión en la app (teléfono y PC) o en la página real (PC), envío tras aprobar | 5 aplicaciones propias enviadas sin error | Pendiente |
| 4 | Lever, Ashby, modo automático con frenos, límite diario, páginas legales | Checklist legal completo | Pendiente |

## Lo que hay (fase 2)

`app/services/apply_agent/`:

- `greenhouse.py`: lee el formulario por `boards-api.greenhouse.io/.../jobs/{id}?questions=true`.
  Sin navegador. Las ofertas europeas (`job-boards.eu.greenhouse.io`) se leen por el mismo host.
- `classify.py`: clase de cada pregunta (identidad, documento, consentimiento,
  sensible, salario, autorización, abierta, opción, texto), tema para emparejar
  respuestas guardadas en español con preguntas en inglés, y detección de
  políticas contra contenido generado con IA.
- `facts.py`: el perfil como hechos citables. Lo único que el agente puede usar.
- `draft.py`: tres pasadas (determinista, LLM solo con hechos, cierre) y los
  motivos de revisión que frenarían el modo automático.

Endpoints (`app/api/v1/routers/apply_agent.py`):

- `POST /applications/{id}/draft` prepara o rehace el borrador (solo Greenhouse por ahora).
- `GET /applications/{id}/draft` lee el último.
- `GET /apply-agent/readiness` dice qué le falta al perfil.

Tabla `application_drafts` (migración 0019 + `db/schema.sql`).

Llenador con navegador (`app/services/apply_agent/filler.py`, contenedor
`backend/Dockerfile.agent`): abre el formulario de Greenhouse en Chromium sin
interfaz, llena lo que el borrador tiene listo y saca una captura. Nunca pulsa
enviar y además aborta cualquier POST de envío. `--safe` escribe datos ficticios
en vez de los del usuario (un formulario de terceros puede registrar lo que se
teclea aunque no se envíe).

### Reglas que el código hace cumplir

- Consentimientos y declaraciones: nunca los responde el agente.
- Datos personales que el perfil no registra (si ya trabajó o se postuló en la
  empresa, relaciones con funcionarios, quién lo refirió, acuerdos con su
  empleador, su usuario en otra plataforma): nunca.
- Autorización de trabajo, patrocinio y salario: solo desde una respuesta
  guardada por el usuario. País, zona horaria y ubicación sí se deducen del perfil.
- Las respuestas guardadas en texto van al LLM como pista (están en español y
  el formulario casi siempre en inglés); solo se copian tal cual si la empresa
  prohíbe la IA y el tema es el mismo.
- Preguntas sensibles (diversidad, salud, nacionalidad, edad...): nunca. Si son
  voluntarias se dejan en blanco; si son obligatorias, las responde el usuario.
  *Ajuste respecto al plan:* una voluntaria en blanco no frena el modo
  automático, porque dejarla en blanco ya es la respuesta prudente; casi todos
  los formularios de EE. UU. traen las EEOC voluntarias y, si no, el modo
  automático no se activaría nunca.
- Si el formulario tiene una política contra IA (Canonical, Anthropic, Twilio
  en el banco), el LLM no participa: solo se llena lo que viene tal cual del perfil.
- El LLM no recibe el correo ni el teléfono, y una opción que no existe en el
  formulario se descarta (en selección múltiple: todas válidas o ninguna).

### Errores que el banco ya cazó (con test de regresión)

- La pregunta de viajes de Canonical menciona "visas" y se contestaba con la
  respuesta guardada sobre patrocinio. El tema ahora sale de la pregunta en sí
  (`question_core`), no del contexto.
- GitLab: "Are you subject to any employment agreements... with your current
  employer?" se llenaba con el nombre de la empresa. Las etiquetas de identidad
  ahora tienen que ser cortas.
- Preguntas de país sin la palabra "which/what" no se marcaban para revisión.
- Con IA (gemma4:26b local), el modelo contestaba "No" a "¿necesitas
  patrocinio?" sin respuesta guardada, "No" a "¿eres funcionario o pariente de
  uno?", "No" a "¿te refirió un directivo?", sacaba el usuario de GitLab del de
  GitHub y redactaba un "I understand..." para un aviso de Anthropic. Todo
  eso ahora lo bloquea el código (clase `personal`, autorización solo con
  respuesta guardada, avisos como consentimiento), no solo el prompt.
- Coinbase publica en su propia web (`coinbase.com/careers/...?gh_jid=`) y la
  URL de Greenhouse redirige allí: el llenador usa la URL de incrustar
  (`form_url`), que sirve el mismo formulario.
- El "Location" de Greenhouse es un autocompletado con id `candidate-location`,
  no el nombre que da la API.

### Hallazgos para la fase 3

- Greenhouse pinta un campo "Country" obligatorio junto al teléfono que no
  viene en la API. El llenador lo completa; el borrador todavía no lo muestra.
- Todos los formularios del banco traen reCAPTCHA Enterprise invisible, que
  actúa al enviar. Enviar desde el servidor puede quedar bloqueado: el modo
  "revisar en la página real" (el usuario pulsa enviar) es el camino seguro, y
  el envío desde el servidor tiene que pasar el control al usuario si aparece
  un desafío.

## Banco de prueba

```bash
# Exportar tu perfil (solo lectura) a backend/runtime/apply_bench/profile.json
# (gitignoreado), luego, en el entorno dev:
docker compose -p jobpilot-dev --env-file .env --env-file dev.env exec backend \
  python -m app.scripts.apply_bench --facts /app/runtime/apply_bench/profile.json \
  --out /app/runtime/apply_bench/ai
```

Deja `bench.md` con una columna "¿Bien?" por campo llenado. Elige solo 20
ofertas de ingeniería no senior de 8 tableros de Greenhouse (Canonical,
Amplemarket, Anthropic, GitLab, Coinbase, Reddit, Twilio, Grafana Labs).

Para usar el Ollama local en vez de Claude, añade a ese comando
`-e OLLAMA_BASE_URL=http://host.docker.internal:11434 -e OLLAMA_ROUTE=all`.

### Resultado (2026-10-12, perfil real, gemma4:26b local)

| Medida | Valor |
|---|---|
| Formularios leídos | 20 de 20 |
| Campos | 368 |
| Llenados por el agente | 155 (15 de ellos por la IA) |
| Para el usuario | 148 (consentimientos, sensibles, datos personales, respuestas guardadas vacías) |
| Con política contra IA | 7 (Canonical, Anthropic, Twilio) |
| Aptos para envío automático | 0 (todos piden al menos un consentimiento) |
| Llenado real con navegador, modo seguro | 175 de 175 campos, 0 fallos, 0 intentos de envío |
| Formularios con reCAPTCHA | 17 de 20 |

La calificación campo por campo (la puerta del 90 %) la hace el usuario en
`backend/runtime/apply_bench/ai/bench.md`.

## Pendiente

- [ ] Completar en Perfil las respuestas guardadas vacías: autorización de
      trabajo, patrocinio de visa, salario, disponibilidad y "¿por qué esta
      empresa?" (`GET /apply-agent/readiness` las lista).
- [ ] Calificar `bench.md` (puerta de la fase 2: 90 %).
- [x] Llenado real con navegador, sin enviar, y captura de pantalla
      (`Dockerfile.agent` + `filler.py`).
- [ ] Mostrar en el borrador el "Country" que Greenhouse añade fuera de la API.
- [ ] Pantalla de revisión del borrador en la app (fase 3).
- [ ] La clave de Anthropic de `.env` devuelve 401 (`invalid x-api-key`): todas
      las funciones de IA de producción están cayendo a su ruta sin IA.
- [ ] Tras mezclar: aplicar `db/schema.sql` a `jobflow_test` de producción
      (`README.md` del backend), o el pre-commit fallará en los tests nuevos.
