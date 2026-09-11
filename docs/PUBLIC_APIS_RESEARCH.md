# Investigación: APIs públicas de empleo

Criterio de inclusión original: **cero fricción de acceso** — sin API key, sin OAuth, sin registro
obligatorio, sin credenciales de ningún tipo. Verificado contra la documentación oficial de cada
plataforma (o, cuando no existe documentación oficial, contra el comportamiento real del endpoint) en
2026-09. Ampliado en 2026-09 con una revisión de fiabilidad de las fuentes que sí requieren registro —
de esa revisión, Adzuna y USAJobs se integraron (France Travail también se integró y se probó, pero se
quitó después por decisión explícita del usuario: solo cubre el mercado laboral francés y no habla
francés); el resto quedó documentado como descartado, con el motivo.

## Resumen

| # | Plataforma | Auth | ¿Integrada? |
|---|---|---|---|
| 1 | Himalayas | Ninguna | Sí (ya estaba) |
| 2 | Arbeitnow | Ninguna | Sí |
| 3 | Remotive | Ninguna | Sí |
| 4 | Jobicy | Ninguna | Sí |
| 5 | RemoteJobs.org | Ninguna | Sí |
| 6 | The Muse | Opcional (funciona sin ella) | Sí |
| 7 | We Work Remotely | Ninguna (RSS público) | Sí (2026-09) |
| 8 | Hacker News — "Who is hiring?" | Ninguna (API Algolia oficial) | Sí (2026-09) |
| 9 | Adzuna | API key gratis (registro instantáneo) | Sí (2026-09) — activa, con clave real del usuario |
| 10 | USAJobs | API key gratis (registro instantáneo) | Sí (2026-09) — activa, con clave real del usuario |
| 11 | Get on Board | Ninguna (facet pública de su API) | Sí (2026-09) |
| 12 | SerpApi (Google Jobs) | API key gratis (registro instantáneo) | Sí (2026-09) |
| 13 | Working Nomads | Ninguna | Sí (2026-09) |
| 14 | Remote OK | Ninguna | Sí (2026-09) — **reevaluada**, ver nota |
| — | France Travail (ex-Pôle Emploi) | OAuth2 client credentials (registro instantáneo) | **No** — se integró y probó, pero se quitó (ver nota) |
| — | RemoteOK | Ninguna en teoría | **No** — ver nota |
| — | Reed.co.uk | API key gratis | **No** — ver nota |
| — | JSearch (RapidAPI) | API key gratis (cuota mínima) | **No** — ver nota |
| — | Jooble | Aprobación manual | **No** — ver nota |
| — | Findwork.dev | API key gratis | **No** — ver nota |
| — | InfoJobs | Basic Auth (client_id/secret) | **No** — registro de apps nuevas cerrado por InfoJobs (2026-09), ver nota |
| — | Seek | Revisión manual (hasta 10 días hábiles) | **No** — ver nota |

Excluidas de raíz (fuera del alcance de esta app, no por fiabilidad): Careerjet (requiere `affid`
registrado), Google Jobs (vía SerpApi), Upwork, LinkedIn e Indeed. **Google Jobs y Upwork ya estuvieron
integrados como opciones separadas ("con credenciales") en una versión anterior de la app, pero se
quitaron por decisión explícita.** LinkedIn e Indeed se investigan a fondo en la sección siguiente porque
el resultado no es un simple "pide key": ninguna de las dos ofrece siquiera una API de búsqueda.

### Por qué se integraron Adzuna y USAJobs (y por qué France Travail se quitó después)

Las 8 fuentes sin registro ya cubren bien empleo remoto/tech global; estas sumaban justo lo que faltaba
con fricción mínima: registro **instantáneo** (llave al momento, sin aprobación manual), cuota gratuita
real (no un tier de juguete), y cobertura que las otras 8 no tienen — Adzuna (agregador multi-país, roles
no-tech incluidos), USAJobs (empleo federal de EE.UU., dato único). El código de ambas está integrado,
probado con claves reales del usuario, y activo (`backend/app/services/adzuna.py`, `usajobs.py`) — cada
una se activa automáticamente en cuanto sus claves se agregan a `.env` (ver `.env.example`); sin claves,
esa fuente simplemente no aparece en los resultados (mismo patrón de "degradación elegante" que
SMTP/Claude/Firebase en el resto de la app).

**France Travail** siguió el mismo camino — se integró y se probó en vivo (con OAuth2 client credentials
reales) — pero el usuario pidió quitarla después de que quedó configurada: solo cubre el mercado laboral
**francés**, y no habla francés, así que no le servía de nada aunque funcionara perfecto técnicamente.
Se quitó el código (`backend/app/services/francetravail.py` y su test ya no existen) — el valor del enum
`job_source` en la base de datos ya migrada se dejó tal cual (Postgres no permite quitar un valor de ENUM
sin recrear el tipo, y no hay ningún trabajo real que lo use, así que dejarlo ahí es inofensivo — mismo
criterio que los valores legado `google_jobs`/`upwork`/`linkedin`/`indeed` de una versión anterior de la
app).

### Por qué se descartaron las demás

- **Reed.co.uk**: buena cobertura de Reino Unido, pero los términos generales del sitio dicen que el uso
  comercial "no está permitido" sin una excepción clara para la API — habría que confirmarlo por escrito
  con Reed antes de depender de ella.
- **JSearch (RapidAPI)**: la cobertura más amplia de todas (agrega LinkedIn, Indeed, Glassdoor,
  ZipRecruiter, Google Jobs), pero el tier gratis es de ~200 solicitudes/mes — solo alcanza para probarla,
  no para producción, y RapidAPI como plataforma tiene quejas de soporte.
- **Jooble**: requiere aprobación manual (formulario revisado por Jooble) y la llave gratis reportada es
  de ~500 solicitudes **de por vida**, no mensuales.
- **Findwork.dev**: se solapa mucho con fuentes que ya están integradas directamente (Hacker News y
  boards similares) y su página de límites devolvió 404 durante la revisión — señal débil de
  mantenimiento.
- **InfoJobs**: la investigación inicial decía que requería un flujo OAuth2 completo pensado para
  partners de negocio establecidos — al revisarlo mejor, la auth real es solo HTTP Basic Auth con
  `client_id`/`client_secret` (nada de OAuth2 completo, tan simple como Adzuna/USAJobs). Pero al intentar
  registrar una app en https://developer.infojobs.net/ (2026-09), su panel "Manage Apps" muestra: *"The
  registration of new apps is currently unavailable. We hope to offer it again in shortly."* — registro de
  apps nuevas cerrado del lado de InfoJobs, nada que se pueda resolver de este lado. Reintentar más
  adelante si se necesita cobertura de España/Italia/Brasil.
- **Seek**: proceso de "Integration Request" con revisión manual por un Partner Manager que puede tardar
  hasta 10 días hábiles — pensado para partners de reclutamiento, no para una app personal. Cobertura
  limitada a Australia/Nueva Zelanda.

**Nota sobre RemoteOK**: expone `https://remoteok.com/api` sin exigir key, pero su CDN (Cloudflare)
bloquea agresivamente peticiones sin un `User-Agent` de navegador real y no tiene documentación oficial
estable (los nombres de campo circulan solo por scrapers de terceros). Por confiabilidad no se integró en
este primer corte — queda documentada como candidata si más adelante se justifica el esfuerzo de
verificarla en producción.

### Reevaluación de RemoteOK (2026-09) — ahora sí integrada

La nota original la descartó porque su CDN bloquea peticiones sin un `User-Agent` de navegador real.
Al re-verificarla en vivo resultó que **ese era justamente el caso**: el `USER_AGENT` compartido del
proyecto ya es una cadena de navegador, así que responde 200 con ~100 vacantes actuales. La otra
objeción —"los nombres de campo circulan solo por scrapers de terceros"— tampoco se sostuvo: el
payload es autodescriptivo (`position`, `company`, `tags`, `salary_min`, `epoch`, `url`,
`apply_url`), no hubo que adivinar nada.

**Sus términos y cómo se cumplen.** El primer elemento de la respuesta trae un aviso `legal` que pide
enlazar de vuelta a la ficha en Remote OK y nombrarlos como fuente, bajo pena de suspender el acceso.
Ambas cosas se cumplen: `source_url` apunta a la página de Remote OK (`url`) y **nunca** al
`apply_url` del empleador, así que el botón "Aplicar en el sitio original" manda tráfico a Remote OK
—exactamente lo que piden—; y el nombre del proveedor se muestra en cada tarjeta de Discover. La
parte de "follow, no nofollow" es sobre SEO de un sitio público y no tiene equivalente en una app
privada de un solo operador.

### Working Nomads (2026-09)

`https://www.workingnomads.com/api/exposed_jobs/` — sin clave, sin registro, sin bloqueo de CDN
(responde 200 con el `User-Agent` propio del proyecto). Devuelve el board completo en un solo array
JSON, con empresa, título, descripción, ubicación, tags y URL. No acepta parámetro de búsqueda, así
que el filtrado se hace localmente sobre el feed cacheado, igual que We Work Remotely y Hacker News.

### Descartadas en esta segunda ronda

- **EU Remote Jobs**: su RSS responde 403 al `User-Agent` del proyecto (mismo bloqueo por el que se
  había descartado RemoteOK) y el feed de WordPress no trae la empresa como campo estructurado.
- **SmartRecruiters**: su búsqueda global pública devuelve 404; solo expone los postings por empresa.
- **Arbeitsagentur (Alemania)**: 403 incluso con la API key pública documentada de su app móvil.
- **Greenhouse / Ashby**: **funcionan sin auth** (verificado: 200 con datos reales), pero son por
  empresa, no por búsqueda — habría que curar una lista de compañías. Quedan como la mejor candidata
  para una próxima ronda, porque son la fuente canónica (el ATS real de la empresa), sin el retraso
  de un agregador.

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

## 7. We Work Remotely

- **Endpoint**: `GET https://weworkremotely.com/remote-jobs.rss` (más feeds por categoría, ej. `.../categories/2-programming.rss`)
- **Auth**: ninguna — es un RSS público, condición de uso: enlazar de vuelta al listado original (se cumple automáticamente, `source_url` siempre es la página real de WWR)
- **Formato**: XML/RSS 2.0. Cada `<item>` trae `title` ("Empresa: Puesto"), `region`, `country`, `type`, `description` (HTML), `pubDate`, `guid` (= URL del puesto)
- **Ubicación**: 100% remoto por naturaleza del sitio; `region` es texto libre (ej. "Worldwide", "Latin America Only")
- **Nivel de experiencia**: no expone campo nativo → heurística de texto (`job_importer.parse_job_text_heuristic`)
- **Límites**: el propio `ttl` del feed es 60 min → se cachea por esa misma ventana en vez de re-pedir el feed completo (~50 avisos) en cada búsqueda
- **Implementación**: `backend/app/services/weworkremotely.py`

## 8. Hacker News — "Who is hiring?"

- **Endpoint**: API Algolia oficial de HN (`hn.algolia.com/api/v1`), no la Firebase API cruda — un solo `GET /items/{id}` trae el hilo completo con todos los comentarios anidados
- **Auth**: ninguna
- **Cómo se ubica el hilo del mes**: `GET /search_by_date?tags=story,author_whoishiring` y se toma el primer resultado cuyo título empiece con "Ask HN: Who is hiring?" (el hilo hermano "Who wants to be hired?" es del lado candidato, no de vacantes)
- **Formato**: cada comentario de primer nivel es una vacante en **texto libre**, por convención de la comunidad (no forzada) "Empresa | Puesto | Ubicación | Tipo | Salario | URL" en la primera línea. Se parsea con un heurístico propio (split por `|` + `job_importer.parse_job_text_heuristic` sobre el resto) — no es tan confiable como un JSON estructurado, pero es la única fuente 100% gratis y sin auth de este tipo
- **Ubicación**: variable, texto libre por posting; muchas veces remoto pero no siempre
- **Nivel de experiencia**: no expone campo nativo → heurística de texto
- **Límites**: el hilo solo recibe comentarios nuevos los primeros días del mes, después queda estático — se cachea 6 horas
- **Implementación**: `backend/app/services/hackernews.py`

## 9. Adzuna

- **Endpoint**: `GET https://api.adzuna.com/v1/api/jobs/{país}/search/{página}` — no existe un endpoint global; hay que pedir por país (`us`, `gb`, `es`, `mx`, `de`, `fr`, `au`, ... ~20 países soportados)
- **Auth**: `app_id` + `app_key`, gratis, registro instantáneo (llegan por correo al momento) en https://developer.adzuna.com/
- **Cuota gratis**: 1,000 llamadas/mes
- **Formato**: JSON — `results[]` con `title`, `company.display_name`, `location.display_name`, `description`, `redirect_url`, `created`, `salary_min/max`, `contract_time` (full_time/part_time), `category.label`
- **Ubicación**: no distingue remoto/presencial de forma nativa — se infiere heurísticamente del título/ubicación (igual que RemoteJobs.org)
- **Nivel de experiencia**: no expone campo nativo → heurística de texto
- **Límites de términos**: los términos de Adzuna prohíben redistribuir/revender los datos crudos en bloque — mostrar resultados de búsqueda dentro de la app (lo que hace JobPilot) es el uso normal y esperado
- **Implementación**: `backend/app/services/adzuna.py` — **funciona en cuanto se agreguen `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` a `.env`**

## 10. USAJobs

- **Endpoint**: `GET https://data.usajobs.gov/api/search`
- **Auth**: `Authorization-Key` (llave gratis) + header `User-Agent` con el correo registrado — ambos exigidos en cada request, gratis, registro instantáneo en https://developer.usajobs.gov/
- **Formato**: JSON — `SearchResult.SearchResultItems[].MatchedObjectDescriptor` con `PositionTitle`, `OrganizationName`, `PositionLocationDisplay`, `PositionURI`, `PositionRemuneration[]`, `PositionSchedule[].Name`, resumen del puesto en `UserArea.Details.JobSummary`
- **Ubicación/alcance**: **solo empleo del gobierno federal de EE.UU.** — no es un agregador general, es la fuente oficial y única de este tipo de vacante; casi ninguna es remota, así que con el filtro por defecto de Discover (`remote_type=remote`) normalmente no aparece nada de USAJobs a menos que se busque explícitamente sin ese filtro
- **Nivel de experiencia**: no expone campo nativo → heurística de texto
- **Límites**: rate limit razonable por `User-Agent` registrado, sin costo — al ser una API de datos públicos del gobierno, es de las más estables/duraderas posibles
- **Implementación**: `backend/app/services/usajobs.py` — **funciona en cuanto se agreguen `USAJOBS_API_KEY`/`USAJOBS_USER_AGENT` a `.env`**

## ~~France Travail (ex-Pôle Emploi)~~ — integrada, probada y luego quitada

Se implementó y se probó en vivo con credenciales OAuth2 reales (`backend/app/services/francetravail.py`,
ya no existe). Cubría **todo el mercado laboral francés** — pero solo francés, y el usuario no habla el
idioma, así que la vacante quedaba inservible sin importar qué tan bien funcionara la integración. Se quitó
por pedido explícito ("elimina la de France Travail, no hablo francés") una vez confirmado que el resto del
pipeline (Adzuna, USAJobs, SerpApi) seguía funcionando sin ella. El valor `francetravail` sigue existiendo
en el ENUM `job_source` de Postgres (no se puede quitar un valor de ENUM sin recrear el tipo) pero ningún
código lo escribe ya — inofensivo, mismo caso que los valores legado de una versión anterior de la app.

## 11. Get on Board

Agregada 2026-09 a partir de una lista de plataformas buenas para alguien buscando trabajo remoto desde
República Dominicana (ver más abajo la nota completa sobre esa lista — Get on Board fue la única de esas
~20 plataformas con una API pública real).

- **Endpoint**: `GET https://www.getonbrd.com/api/v0/search/jobs?query=...` — **no** `GET /jobs` (ese sí exige key y devuelve 401); el endpoint de búsqueda es la "public facet" documentada en su cliente oficial de Ruby y no pide ninguna credencial
- **Auth**: ninguna, para la facet pública. `query` es obligatorio y debe tener 3+ caracteres — sin término de búsqueda válido, este módulo usa `"remote"` como término amplio en vez de fallar
- **Formato**: JSON:API — `data[]` con `attributes.title`, `attributes.description` (HTML), `attributes.remote`/`remote_modality`, `attributes.countries`, `attributes.min_salary`/`max_salary`, relaciones expandibles `company`/`modality`/`seniority` (se piden expandidas con `expand[]=`), y `links.public_url` como URL canónica del puesto
- **Ubicación/alcance**: fuerte en Chile y LatAm en general (empresa chilena); trae también roles 100% remotos abiertos a toda la región — complementa bien a We Work Remotely/Himalayas, que son más globales/US-céntricos
- **Nivel de experiencia**: viene en `seniority.data.attributes.name` (Junior/Senior/etc.) — se normaliza con la misma heurística de palabras clave que el resto
- **Límites**: sin límite documentado públicamente; se cachea 15 min como el resto de fuentes sin auth
- **Implementación**: `backend/app/services/getonbrd.py`

## 12. SerpApi (Google Jobs)

Agregada 2026-09 como respuesta directa a "¿cómo consigo datos de LinkedIn sin arriesgar mi cuenta?" —
ver la sección de LinkedIn más abajo para el porqué de fondo. SerpApi no es una fuente propia: es una capa
sobre el motor "Google for Jobs", que a su vez indexa vacantes públicas de sitios como LinkedIn, Indeed,
Glassdoor y ZipRecruiter (entre muchos otros) porque esos sitios permiten que Google las rastree. Nunca se
toca linkedin.com ni ninguna cuenta — la cuenta del usuario de JobPilot jamás entra en la ecuación.

- **Endpoint**: `GET https://serpapi.com/search.json?engine=google_jobs&q=...`
- **Auth**: `api_key` gratis, registro instantáneo en https://serpapi.com/users/sign_up
- **Cuota gratis**: 250 búsquedas/mes, 50/hora — de sobra para revisión personal periódica (no para
  polling continuo)
- **Formato**: JSON — `jobs_results[]` con `title`, `company_name`, `location`, `description`, `via`
  (el sitio real de origen — `"LinkedIn"`, `"Indeed"`, etc.), `detected_extensions` (`posted_at` relativo
  tipo "3 days ago", `salary`, `schedule_type`, `work_from_home`), `job_highlights[]` (secciones
  "Qualifications"/"Responsibilities" ya estructuradas), `apply_options[]` y `source_link` (URL real del
  posting en el sitio de origen — se usa como `source_url`)
- **Ubicación/alcance**: la cobertura más amplia de todas las 15 fuentes — agrega de facto varios boards
  grandes (incluido LinkedIn) en una sola búsqueda
- **Nivel de experiencia**: no expone campo nativo → heurística de texto sobre título+descripción
- **Límites**: sin paginación real (Google Jobs pagina con un `next_page_token` opaco en vez de un número
  de página) — mismo compromiso que ya asumen Remotive/Jobicy/We Work Remotely/Hacker News (siempre
  `has_more: false`, una sola tanda de resultados por búsqueda)
- **Fechas relativas**: `detected_extensions.posted_at` viene como texto relativo ("3 days ago", "yesterday") en
  vez de una fecha absoluta — se intenta convertir a una fecha real para ordenar, y siempre se guarda el
  texto original en `posted_at_text` para mostrarlo tal cual
- **Implementación**: `backend/app/services/serpapi_jobs.py` — **funciona en cuanto se agregue
  `SERPAPI_API_KEY` a `.env`**

### Sobre la lista de ~20 plataformas "buenas para RD"

Se investigaron Workana, Upwork, Fiverr, Computrabajo RD, Wellfound, Toptal, BairesDev, Turing, Crossover,
Revelo, TECLA, Near, Torre.ai, GetOnBrd, Contra, Deel, LinkedIn, Empleate.gob.do, SuperEmpleo.com.do,
Tecoloco.com.do y OpcionEmpleo.com.do para ver cuáles tenían una fuente de datos (RSS o API) integrable de
la misma forma que las 11 anteriores. El resultado:

- **Get on Board**: única con API pública sin registro → integrada (arriba).
- **Upwork**: sí tiene API (GraphQL), pero el registro exige verificación de negocio/identidad — no es
  autoservicio instantáneo como Adzuna/USAJobs, así que no se integró por ahora.
- **Todas las demás** (Workana, Fiverr, Computrabajo RD, Wellfound, Toptal, BairesDev, Turing, Crossover,
  Revelo, TECLA, Near, Torre.ai, Contra, Deel, LinkedIn, y los 4 portales locales dominicanos): sin
  API/RSS público, o son plataformas de "aplica con tu perfil" (agencias de staffing/freelance) en vez de
  tener listados buscables — no hay forma de traer sus vacantes automáticamente sin hacer scraping (fuera
  de alcance: frágil y en varios casos prohibido explícitamente por sus términos, ej. LinkedIn). Estas
  quedan como accesos directos dentro de la app (sección "Otras plataformas" en Discover) en vez de fuentes
  de búsqueda en vivo — la idea es que sirvan como referencia rápida para aplicar manualmente o negociar
  flexibilidad de ubicación una vez hay una entrevista encaminada, no para traer resultados automáticos.

---

## 13. LinkedIn por sus páginas públicas *(integrada, gratis)*

LinkedIn no da una API de búsqueda de empleos a un proyecto personal (sección siguiente). Las páginas de
empleo que sirve a visitantes sin sesión sí responden sin cuenta ni clave:
`jobs-guest/jobs/api/seeMoreJobPostings/search` devuelve 10 tarjetas de vacantes en HTML y
`jobs-guest/jobs/api/jobPosting/<id>` la ficha con la descripción completa, el nivel y el tipo de empleo.
Portado de la skill `linkedin-search` de [MadsLorentzen/ai-job-search](https://github.com/MadsLorentzen/ai-job-search)
(MIT). El 2026-09-11 reemplazó a la integración con Bright Data, que cobraba por resultado y tardaba
45–90 s por corrida.

- **Auth**: ninguna. Ubicación por defecto cuando Discover no manda una: `LINKEDIN_LOCATION`.
- **Términos**: el acuerdo de usuario de LinkedIn prohíbe el acceso automatizado. No hay ninguna cuenta en
  juego; lo que LinkedIn puede hacer es limitar esta IP por un rato (HTTP 429), que Discover muestra como
  error de esa fuente. Por eso el volumen se mantiene bajo (`backend/app/services/linkedin_jobs.py`): caché
  de 1 h por búsqueda, una sola página de 10 vacantes de la última semana, 3 fichas a la vez, y sin
  palabra clave no se busca.
- **Latencia**: la búsqueda completa (página + 10 fichas) tardó 1.6 s; entra de sobra en el plazo de 12 s
  de Discover.
- **Remoto**: se envía el filtro de modalidad de LinkedIn (`f_WT`: 1 presencial, 2 remoto, 3 híbrido). Las
  tarjetas no traen un campo de modalidad propio, así que la etiqueta sale de ese filtro; si el título
  declara otra modalidad, manda el título.
- **Verificado en vivo** (2026-09-11): "developer" + remoto + República Dominicana devolvió 10 vacantes
  (BairesDev, Flatiron Software, FullStack, BlackStone eIT, Truelogic…), 9 con descripción completa.
- **Campos útiles**: título, empresa, ubicación, fecha, descripción, nivel y tipo de empleo. Las tarjetas
  no traen salario. Si una ficha falla, la vacante sale igual, sin descripción.

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
- **Scraping directo — por qué se descartó explícitamente**: "uso personal" no exime de romper el User
  Agreement (es una prohibición contractual, no distingue por escala/propósito), y el riesgo real e
  inmediato no es legal sino la propia cuenta — LinkedIn detecta y banea cuentas que scrapean, sin importar
  el volumen. `hiQ Labs v. LinkedIn` (sobre si scrapear datos públicos sin login viola la ley CFAA de EEUU)
  no cambia esto: es sobre otra ley, no sobre el contrato de LinkedIn, y menos aún protege a alguien
  scrapeando con su propia cuenta logueada.
- **Vía legítima encontrada**: SerpApi/Google Jobs (ver fuente #13 arriba) — Google indexa públicamente
  páginas individuales de vacantes de LinkedIn (LinkedIn lo permite), y SerpApi expone ese índice ya
  agregado. La cuenta de LinkedIn del usuario nunca se toca — es Google el que rastrea, no nosotros ni
  SerpApi scrapeando LinkedIn directamente. Cobertura parcial (solo lo que Google ya indexó), pero sin el
  riesgo de cuenta.

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

- El endpoint **`GET /jobs/search/aggregate`** dispara las 15 fuentes **en paralelo**
  (`asyncio.gather`) y devuelve un solo listado combinado — así es como Discover muestra "todos los
  resultados de todas las APIs integradas" en una sola búsqueda, sin que el usuario tenga que elegir
  proveedor uno por uno. Un proveedor que falla no tumba a los demás: se reporta por separado — esto
  incluye a Adzuna/USAJobs/SerpApi sin claves configuradas, que simplemente aparecen con 0
  resultados y un mensaje "no configurado" en vez de un error duro.
- **Nivel de experiencia**: taxonomía interna `internship | entry | mid | senior | lead`
  (`backend/app/services/experience_level.py`). Himalayas y The Muse lo mandan como parámetro nativo al
  proveedor; Jobicy lo trae en la respuesta (`jobLevel`) y se normaliza; Arbeitnow/Remotive/RemoteJobs.org
  no lo exponen, así que se infiere por heurística de texto sobre título+descripción (mismo enfoque que ya
  usa `job_importer.py` para seniority) — mismo filtro, aplicado de forma uniforme sobre las 15 fuentes.
- **Ubicación por defecto**: el campo de ubicación en el formulario de Discover arranca con `"Remote"`
  precargado (no es una restricción dura — el usuario puede borrarlo o cambiarlo).
