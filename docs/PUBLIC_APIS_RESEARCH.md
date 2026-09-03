# Investigación: APIs públicas de empleo sin autenticación

Criterio de inclusión: **cero fricción de acceso** — sin API key, sin OAuth, sin registro obligatorio,
sin credenciales de ningún tipo. Verificado contra la documentación oficial de cada plataforma (o, cuando
no existe documentación oficial, contra el comportamiento real del endpoint) en 2026-09.

## Resumen

| # | Plataforma | Auth | ¿Integrada? |
|---|---|---|---|
| 1 | Himalayas | Ninguna | Sí (ya estaba) |
| 2 | Arbeitnow | Ninguna | Sí (nueva) |
| 3 | Remotive | Ninguna | Sí (nueva) |
| 4 | Jobicy | Ninguna | Sí (nueva) |
| 5 | RemoteJobs.org | Ninguna | Sí (nueva) |
| 6 | The Muse | Opcional (funciona sin ella) | Sí (nueva) |
| — | RemoteOK | Ninguna en teoría | **No** — ver nota |

Excluidas de raíz por requerir API key/OAuth/partnership: Adzuna, Reed.co.uk, USAJobs, Jooble,
Findwork.dev, Careerjet (requiere `affid` registrado), Google Jobs (vía SerpApi), Upwork, LinkedIn e Indeed.
**Google Jobs y Upwork ya estuvieron integrados como opciones separadas ("con credenciales") en una versión
anterior de la app, pero se quitaron por decisión explícita** — la app hoy solo trabaja con las 6 fuentes
sin autenticación de esta tabla. LinkedIn e Indeed se investigan a fondo en la sección siguiente porque el
resultado no es un simple "pide key": ninguna de las dos ofrece siquiera una API de búsqueda.

**Nota sobre RemoteOK**: expone `https://remoteok.com/api` sin exigir key, pero su CDN (Cloudflare)
bloquea agresivamente peticiones sin un `User-Agent` de navegador real y no tiene documentación oficial
estable (los nombres de campo circulan solo por scrapers de terceros). Por confiabilidad no se integró en
este primer corte — queda documentada como candidata si más adelante se justifica el esfuerzo de
verificarla en producción.

---

## 1. Himalayas *(ya integrada — resumen para contexto)*

- **Endpoint**: `GET https://himalayas.app/jobs/api/search`
- **Parámetros relevantes**: `q`, `country`, `worldwide` (bool), `seniority` (`Entry-level,Mid-level,Senior,Manager,Director,Executive`, separado por comas), `employment_type`, `sort`, `page`
- **Formato**: JSON `{jobs: [...], totalCount, offset, limit}`
- **Límites**: sin límite documentado explícito; buen ciudadano = cachear y no golpear en loop
- **Implementación**: `backend/app/services/himalayas.py` (sin cambios en este trabajo)

## 2. Arbeitnow

- **Endpoint**: `GET https://www.arbeitnow.com/api/job-board-api`
- **Auth**: ninguna
- **Parámetros**: `page` (paginación; la respuesta trae `links.next` con la URL de la siguiente página lista para usar)
- **Formato de respuesta**:
  ```json
  {
    "data": [
      {
        "slug": "string", "company_name": "string", "title": "string",
        "description": "string (HTML)", "remote": true, "url": "string",
        "tags": ["string"], "job_types": ["string"], "location": "string",
        "created_at": 1234567890
      }
    ],
    "links": {"next": "https://www.arbeitnow.com/api/job-board-api?page=2"},
    "meta": {"current_page": 1}
  }
  ```
- **Ubicación**: campo `location` es texto libre (mercado alemán/europeo mayormente); `remote: true/false` indica remoto
- **Nivel de experiencia**: no expone campo ni parámetro nativo → se infiere por heurística de texto (ver `experience_level.py`)
- **Limitaciones**: sin límite de tasa documentado; sin garantía de estabilidad de campos al no tener versión de API explícita

## 3. Remotive

- **Endpoint**: `GET https://remotive.com/api/remote-jobs`
- **Auth**: ninguna
- **Parámetros**: `category` (nombre o slug — lista en `GET /api/remote-jobs/categories`), `company_name`, `search`, `limit`
- **Formato de respuesta**:
  ```json
  {
    "job-count": 10,
    "jobs": [
      {
        "id": 123, "url": "...", "title": "...", "company_name": "...",
        "company_logo": "...", "category": "Software Development",
        "job_type": "full_time", "publication_date": "2026-01-01T00:00:00",
        "candidate_required_location": "USA Only",
        "salary": "$80,000 - $110,000", "description": "... (HTML)"
      }
    ]
  }
  ```
- **Ubicación**: `candidate_required_location` (texto libre, ej. "USA Only", "Worldwide") — todo el catálogo es remoto por naturaleza del sitio
- **Nivel de experiencia**: no expone campo/parámetro nativo → heurística de texto
- **Limitaciones importantes**: **máx. 2 requests/minuto** (bloqueo si se excede); uso recomendado ≤4 veces al día; **obliga atribución visible a Remotive** y prohíbe re-publicar en agregadores de terceros tipo Google Jobs/LinkedIn — se respeta cacheando agresivamente y mostrando la atribución en la UI

## 4. Jobicy

- **Endpoint**: `GET https://jobicy.com/api/v2/remote-jobs`
- **Auth**: ninguna ("No account or authentication header is required")
- **Parámetros**: `count` (1–200, default 200), `geo` (slug: `usa`, `canada`, `europe`, ...), `industry` (slug: `engineering`, `marketing`, `data-science`, ...), `tag` (keyword)
- **Formato de respuesta**: array de objetos con `id`, `url`, `jobTitle`, `companyName`, `companyLogo`, `jobIndustry[]`, `jobType[]`, `jobGeo`, `jobLevel`, `jobExcerpt`, `jobDescription` (HTML), `pubDate`, `salaryMin`/`salaryMax`/`salaryCurrency`/`salaryPeriod`
- **Ubicación**: todo el catálogo es remoto; `jobGeo` indica elegibilidad geográfica
- **Nivel de experiencia**: **campo nativo `jobLevel`** — se usa directamente (normalizado a la taxonomía interna)
- **Limitaciones**: fair-use — "no más de una vez por hora" para checks automatizados; cachear resultados

## 5. RemoteJobs.org

- **Endpoint**: `GET https://remotejobs.org/api/v1/jobs`
- **Auth**: ninguna ("No account required — just start making requests")
- **Parámetros**: `limit` (1–50, default 20), `offset`, `category`, `type` (`full-time`/`part-time`/`contract`/`freelance`), `q`
- **Formato de respuesta**: `id`, `title`, `url`, `apply_url`, `company{name,logo_url,website,url}`, `category{name,slug}`, `location`, `salary_min`/`salary_max`/`salary_text`, `type`, `description`, `posted_at`
- **Ubicación**: catálogo 100% remoto; no hay filtro geográfico adicional
- **Nivel de experiencia**: no expone campo/parámetro nativo → heurística de texto
- **Limitaciones**: máx. 50 resultados por request; pide atribución visible "Powered by RemoteJobs.org"

## 6. The Muse

- **Endpoint**: `GET https://www.themuse.com/api/public/jobs`
- **Auth**: **opcional** — sin `api_key` el límite es 500 req/hora (suficiente para uso personal); con key gratuita registrada sube a 3,600 req/hora. Al no ser obligatoria, cumple el criterio de "sin autenticación requerida"
- **Parámetros**: `page` (requerido), `location`, `level`, `category`, `company`, `descending`
- **Valores válidos de `level`** (¡coincide casi 1:1 con lo que pide el filtro de nivel de experiencia!): `Internship`, `Entry Level`, `Mid Level`, `Senior Level`, `Management`
- **`location` acepta strings libres, incluyendo `"Remote"`** (verificado con una consulta real)
- **Formato de respuesta**:
  ```json
  {
    "page": 0, "page_count": 42, "items_per_page": 20, "total": 830,
    "results": [
      {
        "id": 123, "name": "Senior Backend Engineer", "contents": "... (HTML)",
        "type": "Full Time", "publication_date": "2026-01-01",
        "company": {"id": 1, "name": "Acme", "short_name": "acme"},
        "locations": [{"name": "Remote"}],
        "levels": [{"name": "Senior Level", "short_name": "senior"}],
        "categories": [{"name": "Engineering"}],
        "tags": ["..."],
        "refs": {"landing_page": "https://www.themuse.com/jobs/..."}
      }
    ]
  }
  ```
- **Limitaciones**: rate limit por hora (ver arriba); headers `X-RateLimit-Remaining/-Limit/-Reset` en cada respuesta para monitorear consumo

---

## Investigación adicional: ¿cómo se consigue acceso a las APIs de Indeed y LinkedIn?

Respuesta corta: **no es un trámite de "pedir una API key"** — ninguna de las dos ofrece hoy una API para
*buscar/leer* vacantes públicamente. Ambas cerraron esa puerta hace años y lo que queda es infraestructura
para que un ATS *publique* empleos en nombre de un empleador ya cliente suyo. Verificado contra la
documentación oficial vigente (Microsoft Learn para LinkedIn, docs.indeed.com para Indeed) en 2026-09.

### LinkedIn — Job Posting API (Talent Solutions)

- **Qué hace realmente**: permite a un ATS o "job distributor" ya aprobado **publicar/sincronizar** vacantes
  hacia LinkedIn en nombre de sus clientes (empleadores). No expone búsqueda ni lectura del catálogo de
  LinkedIn — nunca existió una API pública de búsqueda de empleos en LinkedIn más allá del scraping.
- **Aviso oficial en la documentación (2026)**: *"We are currently not accepting new partnerships for
  LinkedIn's Job Posting API"* — está cerrada a nuevos partners salvo a través de Apply Connect.
- **Quién puede aplicar**: solo **empresas incorporadas** (no desarrolladores individuales ni proyectos
  personales), a través del [formulario de solicitud de partner](https://business.linkedin.com/talent-solutions/ats-partners/partner-application),
  con revisión de un contacto de Business Development de LinkedIn.
- **Requisitos**: firmar un API Agreement con restricciones de uso de datos, cumplir criterios de volumen
  de usuarios y demostrar valor agregado para los miembros de LinkedIn; luego OAuth 2.0 client-credentials
  para las llamadas.
- **Tiempos y tasa de aprobación** (según fuentes de la industria, no oficiales de LinkedIn): proceso de
  3–6 meses, tasa de aprobación menor al 10%.
- **Conclusión**: inviable para un proyecto personal. La única superficie self-serve de LinkedIn para
  desarrolladores individuales es "Sign In with LinkedIn" (autenticación/perfil básico) — no incluye datos
  de empleos.

### Indeed — Job Sync API / Partner APIs

- **Qué hace realmente**: el mismo patrón que LinkedIn. `Job Sync API` es una API GraphQL para que un ATS
  **publique** vacantes de sus clientes en Indeed. Existen además `Indeed Apply` (recibe postulaciones),
  `Disposition Sync API` (reporta el estado de un candidato de vuelta a Indeed) y `Sponsored Jobs API`
  (gestión de campañas pagas) — las cuatro son de publicación/gestión, ninguna de búsqueda.
- **La antigua Publisher API** (la que sí permitía *leer* resultados de búsqueda) **fue deprecada en 2023**
  y no admite nuevos registros — quienes ya la tenían quedaron con acceso heredado, nadie nuevo puede
  solicitarla.
- **Quién puede aplicar**: solo partners de tipo ATS/plataforma de contratación ya establecidos, vía
  [partners.indeed.com](https://partners.indeed.com) (Partner Console) y contacto directo con el equipo de
  partnerships de Indeed — no hay un formulario de autoservicio ni una API key que se pueda generar sin
  esa aprobación previa.
- **Conclusión**: igual de inviable para un proyecto personal — y a diferencia de LinkedIn, aquí ni
  siquiera hay una vía teórica de "búsqueda" en su catálogo oficial, esté abierta o cerrada.

### Qué opciones reales existen si en algún momento se quiere contenido de Indeed/LinkedIn

1. **Vía agregadores que sí licencian ese contenido** (esto es justo lo que hacía la integración de
   Google Jobs que se quitó de esta app): Google Jobs consolida listados originados en LinkedIn, Indeed y
   miles de sitios corporativos y los redistribuye a través de SerpApi con un API key de pago. Es la única
   vía **legítima y documentada** para tocar indirectamente ese contenido sin ser un partner de LinkedIn/Indeed.
2. **Scraping o "normalized JSON APIs" de terceros** (Apify, Bright Data, RapidAPI, HasData, etc.): existen
   y funcionan técnicamente, pero **violan los Términos de Servicio** tanto de LinkedIn como de Indeed —
   ambas compañías han tomado acciones legales activas contra scraping no autorizado (LinkedIn en particular
   litiga esto de forma agresiva). No se recomienda ni se integra nada de esta categoría en esta app.
3. **Convertirse en cliente/partner real**: para LinkedIn, ser cliente de LinkedIn Recruiter y pasar por
   Recruiter System Connect; para Indeed, integrarse como ATS reconocido. Ninguna de las dos rutas aplica a
   un proyecto personal — están pensadas para empresas de software de reclutamiento establecidas.

---

## Cómo se integran (resumen técnico — detalle completo en `backend/README.md`)

- El endpoint **`GET /jobs/search/aggregate`** dispara las 6 fuentes sin auth **en paralelo**
  (`asyncio.gather`) y devuelve un solo listado combinado — así es como Discover muestra "todos los
  resultados de todas las APIs integradas" en una sola búsqueda, sin que el usuario tenga que elegir
  proveedor uno por uno. Un proveedor que falla no tumba a los demás: se reporta por separado.
- **Nivel de experiencia**: taxonomía interna `internship | entry | mid | senior | lead`
  (`backend/app/services/experience_level.py`). Himalayas y The Muse lo mandan como parámetro nativo al
  proveedor; Jobicy lo trae en la respuesta (`jobLevel`) y se normaliza; Arbeitnow/Remotive/RemoteJobs.org
  no lo exponen, así que se infiere por heurística de texto sobre título+descripción (mismo enfoque que ya
  usa `job_importer.py` para seniority) — mismo filtro, aplicado de forma uniforme sobre las 6 fuentes.
- **Ubicación por defecto**: el campo de ubicación en el formulario de Discover arranca con `"Remote"`
  precargado (no es una restricción dura — el usuario puede borrarlo o cambiarlo).
