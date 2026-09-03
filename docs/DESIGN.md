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

### 2.2 Discover — búsqueda en vivo
Pantalla dedicada a buscar vacantes nuevas (a diferencia de Home, que solo recomienda lo ya cargado). Un
selector de proveedor consulta una API externa en tiempo real y muestra resultados normalizados que aún
**no** se guardan (`GET /jobs/search?provider=`); el usuario elige cuáles agregar con un botón "Add to
queue" por resultado:
- **Himalayas** (himalayas.app) — sin API key, funciona out-of-the-box; proveedor por defecto.
- **Google Jobs** (vía SerpApi) — requiere `SERPAPI_API_KEY` del backend; agrega los resultados agregados
  de LinkedIn/Indeed/sitios corporativos que Google Jobs ya consolida, con enlaces de aplicación reales.
- **Upwork** — freelance/contratos; requiere que el usuario conecte su cuenta vía OAuth2 (botón "Conectar
  Upwork" → consentimiento en upwork.com → vuelve a Discover ya conectado).

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

- **Importación de vacantes**: se prioriza el parseo de `JSON-LD` (`schema.org/JobPosting`), presente en la mayoría de portales serios (LinkedIn, Indeed, muchos ATS corporativos como Greenhouse/Lever/Workday); si no existe, fallback heurístico por regex/secciones de texto. Este mismo extractor heurístico se reutiliza para normalizar los resultados de búsqueda en vivo (Himalayas/Google Jobs/Upwork), así que un solo motor de parseo cubre las cuatro fuentes.
- **Búsqueda en vivo**: tres proveedores externos detrás de un único endpoint (`GET /jobs/search?provider=`) — Himalayas (sin key), Google Jobs vía SerpApi (API key de servidor) y Upwork (OAuth2 por usuario, ver `oauth_connections`). Los resultados se cachean brevemente en memoria del proceso para que "agregar a mi cola" no dispare una segunda consulta pagada/limitada al proveedor.
- **Adaptación de CV y cover letters**: motor basado en reglas (offline, siempre funcional) con mejora opcional vía LLM (Claude, `ANTHROPIC_API_KEY`) cuando está configurado — el sistema debe degradar con gracia sin la clave.
- **Match Engine**: fórmula híbrida ponderada (ver detalle técnico en `README.md` raíz y `backend/app/services/match_engine.py`): 50% técnico (overlap de skills), 30% experiencia (años requeridos vs. acumulados relevantes), 20% semántico (similitud texto perfil↔vacante, con fallback TF‑IDF sin dependencia de API externa).
- **Formato ATS-safe**: el CV generado usa estructura de texto plano/simple (secciones estándar, sin tablas/columnas/gráficos), compatible con parsers ATS.
- **Móvil**: la interfaz web es responsive y se sirve como PWA instalable (manifest + iconos); no se requiere una app nativa separada para el MVP — swipe funciona igual de bien vía gestos táctiles en el navegador móvil.
- **Seguridad**: contraseñas con bcrypt, JWT para sesiones, cada usuario solo accede a sus propios datos (perfil, vacantes importadas por él, aplicaciones).

## 5. Flujo de usuario end-to-end

1. Usuario crea cuenta y completa su **CV Maestro** una sola vez.
2. Busca directamente dentro de la app en **Discover** (Himalayas/Google Jobs/Upwork), o si ya encontró algo puntual en otro lado, pega la URL/texto en **Agregar vacante**.
3. El sistema normaliza la vacante y calcula el **match** contra su perfil automáticamente al guardarla.
4. La vacante aparece en la cola de **Home**; el usuario decide en segundos (derecha/izquierda).
5. Al aceptar (derecha), el sistema genera automáticamente un **CV adaptado** y una **cover letter** personalizada para esa vacante.
6. El usuario revisa/edita ambos documentos, los descarga/copia, y aplica en el sitio original.
7. Actualiza el estado en **Aplicaciones** conforme avanza (entrevista, oferta, rechazo), manteniendo todo el historial centralizado.

## 6. Extensiones futuras (fuera del MVP)
- Integración directa con LinkedIn/Indeed (ambos requieren acuerdos comerciales para acceso API, a diferencia de Himalayas/Google Jobs/Upwork ya integrados) para sumarlos como proveedores más en `GET /jobs/search`.
- Exportación directa a PDF con plantillas ATS adicionales.
- Notificaciones/recordatorios de seguimiento de aplicaciones.
- App nativa (React Native) si la PWA resulta insuficiente en el uso real.
