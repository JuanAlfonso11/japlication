# JobFlow AI — Diseño conceptual

Aplicación personal para automatizar y optimizar la búsqueda de empleo: búsqueda/importación consolidada de vacantes, adaptación inteligente de CV, generación de cover letters, y una interfaz de decisión estilo Tinder. Uso en web de escritorio y móvil (PWA responsive).

## 1. Arquitectura general (flujo de pantallas)

El punto de entrada es la recomendación, no el buscador: **Home es el swipe** — lo primero que el usuario
ve al abrir la app son vacantes ya rankeadas contra su CV. Buscar activamente nuevas vacantes es una acción
deliberada, en **Discover**.

```
Login/Registro
      │
      ▼
  Home = Swipe (recomendaciones por CV) ──┬───────────┬───────────┬─────────────────┐
      │                                   │           │           │                 │
      ▼                                   ▼           ▼           ▼                 ▼
Detalle de empleo                    Discover   Agregar vacante  Perfil          Aplicaciones
├─ Match breakdown                  (búsqueda   (URL o texto)  (CV Maestro)      (pipeline)
├─ Generar CV adaptado               en vivo)        │
└─ Generar cover letter                   │           │
      ▲                                   └─────┬─────┘
      └───────────────── ambas alimentan la cola de Home ─┘
```

**Componentes principales**
- `AuthProvider` — sesión/JWT, guard de rutas.
- `ProfileEditor` — formulario estructurado del CV maestro (fuente de verdad factual).
- `SwipeDeck` (Home) — cola de vacantes rankeadas por score, gestos de swipe; primera pantalla tras iniciar sesión.
- `DiscoverSearch` — selector de proveedor + búsqueda en vivo, resultados que el usuario elige agregar a la cola.
- `JobImporter` — captura de URL/texto para una vacante específica ya encontrada en otro lado.
- `MatchEngine (backend)` — calcula compatibilidad perfil↔vacante; se dispara automáticamente al agregar una vacante por cualquier vía, para que aparezca lista en Home sin pasos extra.
- `JobDetail` — descripción completa + acciones de generación (CV/cover letter).
- `ApplicationsBoard` — pipeline de estados (guardado → aplicado → entrevista → oferta/rechazo).

## 2. Diseño de cada pantalla clave

### 2.1 Home (Swipe) — pantalla de entrada
- Lo primero que ve el usuario tras iniciar sesión: una franja compacta de estadísticas (vacantes en cola, aplicadas, en entrevista, ofertas) seguida del mazo de swipe.
- Una tarjeta a la vez: título, empresa, ubicación, score de match, top skills coincidentes/faltantes.
- Swipe derecha (o botón ✓) = guardar/aplicar → pasa a `applications` con estado `saved`.
- Swipe izquierda (o botón ✕) = descartar → estado `passed`, no vuelve a aparecer en la cola.
- Cola ordenada por score descendente; soporta teclado (flechas) para uso rápido en desktop.
- Diseñada mobile-first: es el flujo de mayor fricción y el que más se beneficia de un gesto rápido en el celular.
- Estado vacío ("ya estás al día") enlaza directo a **Discover** para seguir alimentando la cola.
- **Slider de alcance geográfico**: como las vacantes solo traen ubicación en texto libre (sin coordenadas)
  y varias fuentes son 100% remotas sin ubicación fija, en vez de un radio literal en km es un slider de 5
  niveles — Solo remoto / Mi ciudad / Mi región / Mi país / Cualquier lugar — que arranca en "Cualquier
  lugar" (nunca oculta nada por defecto). Al mover el slider a un nivel que necesita ubicación, pide
  geolocalización del navegador y la resuelve a ciudad/región/país vía OpenStreetMap Nominatim (reverse
  geocoding gratis, sin API key), cacheada 24h en `localStorage`. El filtrado es 100% client-side sobre la
  cola ya cargada — una vacante sin ubicación reconocible, o sin ubicación de usuario resuelta todavía,
  nunca se oculta (mismo criterio "mejor mostrar de más que esconder un match real" que el resto de filtros
  de la app).

### 2.2 Discover — búsqueda en vivo
Pantalla dedicada a buscar vacantes nuevas (a diferencia de Home, que solo recomienda lo ya cargado).
Un único botón de búsqueda dispara `GET /jobs/search/aggregate` en paralelo contra las **6 APIs públicas
sin ningún tipo de autenticación** (investigación completa en `docs/PUBLIC_APIS_RESEARCH.md`, incluyendo
por qué Google Jobs y Upwork —ambas con credenciales— se quitaron deliberadamente, y por qué LinkedIn e
Indeed ni siquiera son una opción real para un proyecto personal): **Himalayas, Arbeitnow, Remotive,
Jobicy, RemoteJobs.org y The Muse**. Los resultados de todas se combinan en una sola lista (ordenada por
fecha de publicación), cada tarjeta muestra de qué fuente vino, y si alguna API falla no tumba a las
demás — se reporta aparte y el resto de resultados se sigue mostrando. El usuario elige cuáles agregar
con un botón "Add to queue" por resultado; nada se persiste hasta que hace eso.

**Filtros**: tres selectores independientes en vez de texto libre. **Puesto** es un dropdown agrupado por
disciplina (ingeniería de software, infraestructura y datos, otras ingenierías, producto/diseño, otros
roles) en vez de una caja de texto. **Ubicación** es puramente geográfica (país/región, ej. "Mexico",
"Europe" — vacío significa cualquier lugar) y **Modalidad** (Remoto/Híbrido/Presencial, arranca en
"Remoto" para preservar el comportamiento por defecto histórico) es un filtro aparte e independiente —
antes "ubicación" y "remoto" estaban mezclados en un solo campo con un caso especial para
`location=Remote`; ahora cada proveedor los trata como dos filtros ortogonales
(`backend/app/api/v1/routers/jobs.py`). Un cuarto selector de **Nivel de experiencia** (Practicante,
Junior, Nivel medio, Senior, Liderazgo) filtra las 6 fuentes sin login de forma uniforme — algunas lo
exponen de forma nativa (Himalayas, The Muse mandan el filtro directo al proveedor; Jobicy lo trae en la
respuesta), las que no lo hacen (Arbeitnow, Remotive, RemoteJobs.org) lo infieren por heurística de texto
sobre título+descripción (`backend/app/services/experience_level.py`) — mismo criterio, aplicado parejo
en las 6.

Al agregar un resultado se normaliza, se persiste y se calcula su match automáticamente — reaparece listo
en la cola de **Home** sin pasos adicionales.

### 2.3 Agregar vacante (Import)
Para cuando el usuario ya encontró una vacante específica en otro lado (no está "descubriendo", está
"agregando algo puntual"): pega la URL (`POST /jobs/import`, JSON-LD `JobPosting` con fallback heurístico)
o pega el texto de la descripción directamente. Mismo resultado normalizado + match automático que Discover.

### 2.4 Perfil / CV Maestro
- Editor por secciones: encabezado/resumen, habilidades (nombre, categoría, nivel, años), experiencia (empresa, cargo, fechas, bullets, skills usadas), educación, certificaciones, idiomas.
- Este perfil es la **única fuente de verdad factual** — nunca se sobreescribe automáticamente; las adaptaciones por vacante se generan como *versiones derivadas* (`resume_versions`), preservando el original.
- UX: secciones repetibles (agregar/quitar filas), guardado explícito con indicador de cambios sin guardar.
- **Importar CV en PDF** (`POST /profile/import-cv`): botón arriba del editor para partir de un CV
  existente en vez de teclear todo desde cero. Sube el PDF, el backend extrae el texto y lo estructura
  (con Claude si hay `ANTHROPIC_API_KEY`; si no, con un heurístico que solo saca contacto y habilidades,
  dejando experiencia/educación vacías antes que inventar una estructura que no puede confirmar) y
  **precarga el formulario sin guardar nada todavía** — el usuario revisa, completa lo que falte y recién
  ahí hace clic en Guardar. Mismo principio que el resto de la app: el perfil nunca se sobreescribe a
  ciegas.
- **Auto-búsqueda tras subir CV** (`POST /jobs/search/auto-import`): justo después de que el usuario
  guarda el perfil que acaba de precargar desde un PDF, el frontend dispara automáticamente una búsqueda
  en las 6 fuentes sin login usando el headline (o el cargo más reciente, o las primeras skills como
  respaldo) y **importa y calcula el match** de las vacantes más nuevas de una sola vez — así la cola de
  **Home** ya tiene algo que mostrar sin que el usuario tenga que pasar por Discover primero. Solo se
  cuentan/matchean vacantes realmente nuevas (por `source_url`); guardados posteriores del perfil que no
  vinieron de un CV recién subido no vuelven a disparar la búsqueda.
- **Evaluador de CV** (`GET /profile/evaluation`): tarjeta fija arriba del editor, siempre visible, que responde
  "¿en qué está flaqueando mi CV?" — a diferencia del Match Engine (que compara contra *una* vacante), esto
  evalúa el perfil por sí solo: completitud (¿falta headline, resumen, skills, experiencia?), impacto de los
  logros (¿cuántos bullets tienen métricas vs. frases pasivas tipo "responsable de"?), cobertura de skills
  (¿usaste una skill en tu experiencia que no está en tu lista?), y señales de ATS-safety (emojis, bullets
  demasiado largos, fechas con formato raro). Devuelve un score 0-100 por categoría, una lista priorizada de
  "qué arreglar primero", fortalezas, y un resumen en una o dos frases — se recalcula automáticamente cada vez
  que el usuario guarda cambios en su perfil.

### 2.5 Detalle de vacante + Match
- Descripción completa, requisitos, responsabilidades.
- **Match breakdown visual**: score global + desglose (técnico / experiencia / semántico), skills coincidentes (verde) vs. faltantes (ámbar), y "concerns" en lenguaje natural (p. ej. "Piden 5+ años de liderazgo; tu perfil registra 2").
- Acciones: "Generar CV adaptado" y "Generar cover letter", cada una muestra el resultado editable con copiar/exportar.

### 2.6 Aplicaciones (pipeline)
- Filtros/columnas por estado: guardado, aplicado, entrevista, oferta, rechazado, retirado.
- Cada tarjeta enlaza al detalle de la vacante, al CV usado y a la cover letter enviada; permite anotar seguimiento (notas, fecha de aplicación).

## 3. Conexiones entre módulos

```
Import de empleo → normalización (JSON estructurado) → tabla `jobs`
                                    │
                                    ▼
Perfil (career_profiles) ───► Match Engine ───► job_matches (cache) ───► Home (swipe feed)
                                    │
                        (usuario decide "derecha")
                                    ▼
                              applications
                                    │
                   ┌────────────────┴────────────────┐
                   ▼                                  ▼
        Resume Adapter (usa career_profile      Cover Letter Generator
        + requisitos de la vacante)             (usa perfil + vacante + CV adaptado)
                   │                                  │
                   ▼                                  ▼
           resume_versions                     cover_letters
                   └──────────────┬───────────────────┘
                                  ▼
                     vinculados a la `application` correspondiente
```

La adaptación de CV y la cover letter **siempre parten del perfil maestro + los datos normalizados de la vacante** (nunca del texto crudo/HTML), lo que evita alucinaciones y mantiene veracidad: solo se reordena, enfatiza o reformula lenguaje ya presente en el perfil.

## 4. Consideraciones técnicas

- **Importación de vacantes**: se prioriza el parseo de `JSON-LD` (`schema.org/JobPosting`), presente en la mayoría de portales serios; si no existe, fallback heurístico por regex/secciones de texto. Este mismo extractor heurístico se reutiliza para normalizar los resultados de búsqueda en vivo de las 6 fuentes, así que un solo motor de parseo las cubre a todas.
- **Búsqueda en vivo**: 6 proveedores sin autenticación detrás de un único endpoint agregado (`GET /jobs/search/aggregate`, con `GET /jobs/search?provider=` disponible para consultar uno solo). Los resultados se cachean brevemente en memoria del proceso para que "agregar a mi cola" no dispare una segunda consulta al proveedor.
- **Adaptación de CV y cover letters**: motor basado en reglas (offline, siempre funcional) con mejora opcional vía LLM (Claude, `ANTHROPIC_API_KEY`) cuando está configurado — el sistema debe degradar con gracia sin la clave.
- **Evaluador de CV**: mismo enfoque — reglas explicables y deterministas (`backend/app/services/cv_evaluator.py`) que siempre funcionan sin configuración; el resumen en lenguaje natural usa Claude cuando hay `ANTHROPIC_API_KEY`, con una frase de respaldo determinista si no.
- **Match Engine**: fórmula híbrida ponderada (ver detalle técnico en `README.md` raíz y `backend/app/services/match_engine.py`): 50% técnico (overlap de skills), 30% experiencia (años requeridos vs. acumulados relevantes), 20% semántico (similitud texto perfil↔vacante, con fallback TF‑IDF sin dependencia de API externa).
- **Formato ATS-safe**: el CV generado usa estructura de texto plano/simple (secciones estándar, sin tablas/columnas/gráficos), compatible con parsers ATS.
- **Móvil**: la interfaz web es responsive y se sirve como PWA instalable (manifest + iconos); no se requiere una app nativa separada para el MVP — swipe funciona igual de bien vía gestos táctiles en el navegador móvil.
- **Seguridad**: contraseñas con bcrypt, JWT para sesiones, cada usuario solo accede a sus propios datos (perfil, vacantes importadas por él, aplicaciones). **Verificación de correo**: al registrarse se manda un email con un enlace firmado (JWT de un solo propósito) que el usuario confirma con un clic (`GET /auth/verify-email?token=`); el enlace expira a los **10 minutos** (a propósito, para mayor control) y si se vence el usuario puede pedir uno nuevo con un botón, tanto desde el aviso persistente en la app como desde la propia pantalla de "enlace inválido". El login no se bloquea mientras tanto, para no dejar a alguien fuera de su propia cuenta por un problema de entrega de correo. Sin `SMTP_HOST` configurado, el enlace queda en los logs del backend en vez de enviarse — el flujo se puede probar igual en desarrollo local sin cuenta de correo.

## 5. Flujo de usuario end-to-end

1. Usuario crea cuenta y completa su **CV Maestro** una sola vez.
2. Busca directamente dentro de la app en **Discover** (las 6 fuentes sin login a la vez), o si ya encontró algo puntual en otro lado, pega la URL/texto en **Agregar vacante** — o sube su CV en PDF en **Perfil** para no partir de cero.
3. El sistema normaliza la vacante y calcula el **match** contra su perfil automáticamente al guardarla.
4. La vacante aparece en la cola de **Home**; el usuario decide en segundos (derecha/izquierda).
5. Al aceptar (derecha), el sistema genera automáticamente un **CV adaptado** y una **cover letter** personalizada para esa vacante.
6. El usuario revisa/edita ambos documentos, los descarga/copia, y aplica en el sitio original.
7. Actualiza el estado en **Aplicaciones** conforme avanza (entrevista, oferta, rechazo), manteniendo todo el historial centralizado.

## 6. Extensiones futuras (fuera del MVP)
- LinkedIn e Indeed quedan fuera del alcance de este proyecto: ninguna de las dos tiene una API pública para *buscar* vacantes hoy — ambas cerraron esa puerta hace años y solo queda infraestructura para que un ATS *publique* empleos en nombre de un empleador ya cliente, detrás de programas de partners empresariales (ver investigación completa en `docs/PUBLIC_APIS_RESEARCH.md`).
- Exportación directa a PDF con plantillas ATS adicionales.
- Notificaciones/recordatorios de seguimiento de aplicaciones.
- App nativa (React Native) si la PWA resulta insuficiente en el uso real.
