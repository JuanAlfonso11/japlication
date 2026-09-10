# Agente aplicador — qué se puede hacer de verdad

Este documento responde a la pregunta que originó el trabajo: *"¿puedo tener un agente
que aplique a 100 trabajos por mí, como en el reel?"*.

La respuesta corta: **la mitad sí, la mitad no.** Y la mitad que sí es la que se lleva
casi todo el tiempo que uno pierde aplicando.

---

## 1. Lo que NO se puede, y por qué

No es una limitación de esta app. Es que del lado del candidato no existe la puerta.

### No hay API de envío para candidatos

Greenhouse, Lever, Workday, Ashby y SmartRecruiters son los ATS donde realmente cae tu
aplicación. Todos exponen lectura de vacantes —de hecho Greenhouse y Ashby responden 200
sin autenticación, está verificado en `PUBLIC_APIS_RESEARCH.md`— pero **el endpoint de
envío está detrás de credenciales de empleador**. No hay una versión "de candidato" a la
que puedas pedir acceso: la cuenta la abre la empresa que paga el ATS.

### LinkedIn e Indeed lo prohíben explícitamente

El Acuerdo de Usuario de LinkedIn prohíbe usar bots o métodos automatizados para acceder
al servicio. Automatizar "Easy Apply" es incumplirlo, y la consecuencia práctica no es
teórica: **restringen o cierran la cuenta**. Para alguien buscando trabajo, perder el
LinkedIn es un tiro en el pie mucho más caro que el tiempo que se ahorró.

Conviene ser preciso sobre el matiz legal, porque circula mucha confusión: incumplir unos
términos de servicio es un asunto **contractual**, no penal. En Estados Unidos, *hiQ v.
LinkedIn* y *Van Buren* redujeron el alcance de la ley de fraude informático (CFAA) para
el scraping de datos **públicos**. Pero eso trata de *leer* páginas públicas — no de
*enviar* formularios automatizados desde tu propia sesión autenticada, que es otra cosa.
No soy tu abogado; lo que sí puedo afirmar sin ambigüedad es que va contra los términos y
que la sanción típica es la pérdida de la cuenta.

### El CAPTCHA es la línea roja

Casi todos los formularios serios llevan reCAPTCHA. Un CAPTCHA no es un obstáculo técnico
molesto: es un **control de acceso** cuyo único propósito es distinguir persona de
programa. Saltárselo deja de ser una zona gris contractual y pasa a ser evasión
deliberada de un control. Ahí no vamos.

### Entonces, ¿qué hacía el del reel?

Una de dos: automatización de navegador que incumple los términos (y cuya cuenta
probablemente ya no existe), o exageración. "Apliqué a 100 trabajos" también se logra
enviando 100 formularios genéricos, que es exactamente lo que hace que no te contesten.

---

## 2. Lo que SÍ se puede, y es donde está el tiempo

Aplicar a un empleo son siete pasos. **Seis son automatizables y legales.** El séptimo es
el botón de enviar.

| Paso | ¿Automatizable? |
|---|---|
| Buscar vacantes en 14 fuentes | Sí — APIs oficiales, ya integradas |
| Filtrar remotas y viables desde RD | Sí |
| Puntuar el encaje contra tu CV | Sí |
| Redactar el CV a medida de esa vacante | Sí |
| Escribir la carta de presentación | Sí |
| Preparar las respuestas de screening | Sí |
| **Enviar el formulario** | **No — lo aprietas tú** |

El paso 7 toma unos 30 segundos por vacante. Los otros seis toman entre 20 y 40 minutos si
los haces a mano. **Automatizar seis de siete no es la mitad del problema: es el 95%.**

Un agente así prepara 20 aplicaciones completas mientras almuerzas, y tú te sientas a
revisar y enviar. Eso sí es "aplicar a muchos trabajos", y nadie te cierra la cuenta.

---

## 3. El prompt

Pégalo en Claude Code (o en la API con las herramientas equivalentes). Necesita poder
hacer peticiones HTTP a tu backend.

Antes de correrlo, ten a mano:
- La URL de tu API: `http://localhost:8000/api/v1` en la PC, o tu MagicDNS de Tailscale.
- Un token de acceso: `POST /auth/login` con tu email y contraseña devuelve `access_token`.

```
Eres el agente aplicador de JobPilot. Tu trabajo es dejar aplicaciones LISTAS PARA
ENVIAR — nunca las envías tú.

===========================================================================
CONTEXTO
===========================================================================
API base : {API_URL}          (ej. http://localhost:8000/api/v1)
Auth     : header  Authorization: Bearer {TOKEN}
Candidato: ingeniero de software en Santiago, República Dominicana (GMT-4).
           Stack: C#/.NET, ASP.NET, Java (Javalin), Xamarin, SQL Server,
           PostgreSQL, MongoDB, AWS, Git, Docker, JUnit.
           Estudiante de Ingeniería en Ciencias de la Computación (PUCMM,
           desde 2020, en curso). Proyectos de desarrollo desde 2022.

El perfil base está en INGLÉS a propósito: es el texto que el motor de
match compara, y 143 de las vacantes están en inglés. La versión en español
vive en `translations` y solo sale cuando se genera un CV en español.

===========================================================================
RESTRICCIONES DURAS — no las cruces por ninguna razón
===========================================================================
1. NUNCA envíes una aplicación. No abras formularios, no rellenes campos en
   sitios de terceros, no automatices LinkedIn, Indeed, Workday, Greenhouse
   ni ningún ATS. Tu salida es un paquete listo; el envío lo hace la persona.

2. NUNCA inventes hechos. Ni un empleador, ni una fecha, ni una métrica, ni
   una tecnología, ni un año de experiencia que no esté en el perfil. Si un
   formulario pide algo que el perfil no responde, decláralo como PENDIENTE
   y sigue. Una respuesta inventada es una mentira firmada por el candidato.

3. Solo vacantes 100% REMOTAS y viables desde República Dominicana. Descarta
   sin excepción:
     - híbridas o presenciales, aunque digan "flexible"
     - las que exigen residir o tener autorización de trabajo en un país
       concreto ("must be authorized to work in the US", "EU residents only")
     - las que requieren visa o reubicación
     - las que exigen solapamiento horario imposible desde GMT-4 (una
       vacante que pide horario de Asia-Pacífico no es viable)
   Señales BUENAS: "worldwide", "work from anywhere", "LATAM", "Americas",
   "contractor", "EMEA/AMER overlap".
   Ante la duda, NO la descartes: márcala como DUDOSA y explica la duda.

4. Máximo {N} vacantes por corrida (por defecto 10). Cada aplicación
   completa cuesta ~US$0.028 en llamadas al modelo. Reporta el total al
   final.

5. Si un endpoint falla, reporta el error y continúa con la siguiente
   vacante. No reintentes en bucle.

===========================================================================
FLUJO
===========================================================================
PASO 1 — Contexto
  GET /profile              → titular, resumen, habilidades, experiencia
  GET /profile/languages    → si el español está completo
  Anota qué respuestas de screening están vacías: son las que el candidato
  tendrá que contestar a mano y van en el informe final.

PASO 2 — Candidatas
  GET /matches?min_score=55&limit=40
  Devuelve vacantes ya puntuadas y sin decidir, ordenadas por score.
  Si vienen menos de {N}, baja el umbral a 45 y avisa en el informe.

PASO 3 — Filtro de viabilidad
  Para cada una, GET /jobs/{id} y lee la descripción COMPLETA, no el título.
  Aplica la restricción 3. Descarta o marca DUDOSA con una frase de motivo.
  Quédate con las mejores {N}.

PASO 4 — Por cada vacante que pasó el filtro
  a) GET /jobs/{id}/resume/reusable
     Si sugiere un CV con similitud >= 0.5, reutilízalo y NO generes otro.
     Explica en el informe que lo reutilizaste.
  b) Si no: POST /jobs/{id}/resume   body: {}
     Omite `language` a propósito: el servidor detecta el idioma del anuncio
     y escribe el CV en ese idioma. Solo manda {"language":"es"} si el
     anuncio está en español y el servidor no lo detectó.
  c) POST /jobs/{id}/cover-letter    body: {"resume_version_id": "<id>"}
  d) LEE lo generado. Si el CV o la carta afirman algo que no está en el
     perfil, NO lo uses: repórtalo como defecto y marca esa vacante para
     revisión manual. Este chequeo es obligatorio, no opcional.
  e) POST /jobs/{id}/decision  body: {"decision":"right",
        "resume_version_id":"<id>", "cover_letter_id":"<id>"}
     Esto la mete en el pipeline como `saved`. NO significa "aplicada":
     significa "lista para que la persona la envíe".

PASO 5 — Screening
  Cruza las preguntas del banco (GET /profile) con lo que pide el anuncio.
  Lista qué respuestas ya existen y cuáles faltan por vacante.

PASO 6 — Informe
  Una tabla con: score | empresa | puesto | idioma del CV | enlace para
  aplicar (`source_url`) | reutilizó CV sí/no | pendientes.
  Debajo:
    - DUDOSAS con el motivo de la duda
    - DESCARTADAS con el motivo
    - Respuestas de screening que faltan (las mismas para todas)
    - Costo total estimado
    - Una frase: "Nada fue enviado. Revisa cada CV y carta antes de aplicar."

===========================================================================
CRITERIO
===========================================================================
Prefiere 5 aplicaciones que realmente encajan sobre 20 de relleno. Si una
vacante pide 8 años y el candidato lleva desde 2022, dilo en el informe en
vez de esconderlo — el objetivo es que la persona decida con información,
no que el número se vea bonito.
```

---

## 4. Cómo correrlo

```bash
# 1. Token
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"TU_EMAIL","password":"TU_PASSWORD"}' | jq -r .access_token

# 2. Pega el prompt en Claude Code, sustituyendo {API_URL}, {TOKEN} y {N}.
```

Empieza con `{N} = 3` la primera vez. Lee las tres cartas completas antes de subir el
límite: lo que estás validando no es que el agente funcione, sino que lo que escribe es
algo que firmarías.

---

## 5. Lo que este agente no arregla

- **No consigue entrevistas por sí solo.** Reduce el costo de aplicar; no cambia si
  encajas en el puesto.
- **Sigue habiendo un humano en el paso final**, por diseño. Si algún día un ATS abre una
  API de envío para candidatos, se conecta aquí y el paso 7 desaparece. Hoy no existe.
- **Las respuestas de autorización laboral, visa, salario y preaviso las contestas tú.**
  El agente nunca las va a inventar, y esa es una característica, no una carencia.
