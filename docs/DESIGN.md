# JobFlow AI — Diseño conceptual

Aplicación personal para automatizar y optimizar la búsqueda de empleo: búsqueda/importación consolidada de vacantes, adaptación inteligente de CV, generación de cover letters, y una interfaz de decisión estilo Tinder. Uso en web de escritorio y móvil (PWA responsive).

## 1. Arquitectura general (flujo de pantallas)

```
Login/Registro
      │
      ▼
  Dashboard (Home) ──────────────┬───────────────┬─────────────────┐
      │                          │               │                 │
      ▼                          ▼               ▼                 ▼
Import de empleos          Swipe (matches)   Perfil (CV Maestro) Aplicaciones
(URL o texto)                    │                                 (pipeline)
      │                          ▼
      │                    Detalle de empleo
      │                    ├─ Match breakdown
      │                    ├─ Generar CV adaptado
      │                    └─ Generar cover letter
      └──────────────────────────┘
```

**Componentes principales**
- `AuthProvider` — sesión/JWT, guard de rutas.
- `ProfileEditor` — formulario estructurado del CV maestro (fuente de verdad factual).
- `JobImporter` — captura de URL/texto, muestra el resultado normalizado.
- `MatchEngine (backend)` — calcula compatibilidad perfil↔vacante.
- `SwipeDeck` — cola de vacantes rankeadas por score, gestos de swipe.
- `JobDetail` — descripción completa + acciones de generación (CV/cover letter).
- `ApplicationsBoard` — pipeline de estados (guardado → aplicado → entrevista → oferta/rechazo).

## 2. Diseño de cada pantalla clave

### 2.1 Búsqueda / Importación
- Campo de URL (pega el link de LinkedIn/Indeed/carrera corporativa) → botón "Importar".
- Alternativa: pegar el texto de la descripción directamente (para sitios sin scraping fiable).
- Resultado normalizado mostrado de inmediato: título, empresa, ubicación, tipo de contrato, seniority, requisitos y skills detectadas, con opción de corregir manualmente antes de guardar.
- *Nota de alcance:* la integración "en vivo" con Google Jobs/LinkedIn/Indeed vía sus APIs oficiales requiere acuerdos comerciales o scraping frágil sujeto a bloqueos; el MVP prioriza **importación por URL** (funciona con cualquier fuente que el usuario encuentre) como el mecanismo robusto y legal, dejando la búsqueda federada como extensión futura (ver §6).

### 2.2 Perfil / CV Maestro
- Editor por secciones: encabezado/resumen, habilidades (nombre, categoría, nivel, años), experiencia (empresa, cargo, fechas, bullets, skills usadas), educación, certificaciones, idiomas.
- Este perfil es la **única fuente de verdad factual** — nunca se sobreescribe automáticamente; las adaptaciones por vacante se generan como *versiones derivadas* (`resume_versions`), preservando el original.
- UX: secciones repetibles (agregar/quitar filas), guardado explícito con indicador de cambios sin guardar.

### 2.3 Detalle de vacante + Match
- Descripción completa, requisitos, responsabilidades.
- **Match breakdown visual**: score global + desglose (técnico / experiencia / semántico), skills coincidentes (verde) vs. faltantes (ámbar), y "concerns" en lenguaje natural (p. ej. "Piden 5+ años de liderazgo; tu perfil registra 2").
- Acciones: "Generar CV adaptado" y "Generar cover letter", cada una muestra el resultado editable con copiar/exportar.

### 2.4 Swipe (interfaz de decisión)
- Una tarjeta a la vez: título, empresa, ubicación, score de match, top 3 skills coincidentes/faltantes.
- Swipe derecha (o botón ✓) = guardar/aplicar → pasa a `applications` con estado `saved`.
- Swipe izquierda (o botón ✕) = descartar → estado `passed`, no vuelve a aparecer en la cola.
- Cola ordenada por score descendente; soporta teclado (flechas) para uso rápido en desktop.
- Diseñada mobile-first: es el flujo de mayor fricción y el que más se beneficia de un gesto rápido en el celular.

### 2.5 Aplicaciones (pipeline)
- Filtros/columnas por estado: guardado, aplicado, entrevista, oferta, rechazado, retirado.
- Cada tarjeta enlaza al detalle de la vacante, al CV usado y a la cover letter enviada; permite anotar seguimiento (notas, fecha de aplicación).

## 3. Conexiones entre módulos

```
Import de empleo → normalización (JSON estructurado) → tabla `jobs`
                                    │
                                    ▼
Perfil (career_profiles) ───► Match Engine ───► job_matches (cache) ───► Swipe feed
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

- **Importación de vacantes**: se prioriza el parseo de `JSON-LD` (`schema.org/JobPosting`), presente en la mayoría de portales serios (LinkedIn, Indeed, muchos ATS corporativos como Greenhouse/Lever/Workday); si no existe, fallback heurístico por regex/secciones de texto. Evita depender de APIs pagas para el MVP.
- **Adaptación de CV y cover letters**: motor basado en reglas (offline, siempre funcional) con mejora opcional vía LLM (Claude, `ANTHROPIC_API_KEY`) cuando está configurado — el sistema debe degradar con gracia sin la clave.
- **Match Engine**: fórmula híbrida ponderada (ver detalle técnico en `README.md` raíz y `backend/app/services/match_engine.py`): 50% técnico (overlap de skills), 30% experiencia (años requeridos vs. acumulados relevantes), 20% semántico (similitud texto perfil↔vacante, con fallback TF‑IDF sin dependencia de API externa).
- **Formato ATS-safe**: el CV generado usa estructura de texto plano/simple (secciones estándar, sin tablas/columnas/gráficos), compatible con parsers ATS.
- **Móvil**: la interfaz web es responsive y se sirve como PWA instalable (manifest + iconos); no se requiere una app nativa separada para el MVP — swipe funciona igual de bien vía gestos táctiles en el navegador móvil.
- **Seguridad**: contraseñas con bcrypt, JWT para sesiones, cada usuario solo accede a sus propios datos (perfil, vacantes importadas por él, aplicaciones).

## 5. Flujo de usuario end-to-end

1. Usuario crea cuenta y completa su **CV Maestro** una sola vez.
2. Encuentra una vacante interesante en LinkedIn/Indeed/sitio corporativo → copia la URL → la pega en **Importar**.
3. El sistema normaliza la vacante y calcula el **match** contra su perfil.
4. La vacante aparece en la cola de **Swipe**; el usuario decide en segundos (derecha/izquierda).
5. Al aceptar (derecha), el sistema genera automáticamente un **CV adaptado** y una **cover letter** personalizada para esa vacante.
6. El usuario revisa/edita ambos documentos, los descarga/copia, y aplica en el sitio original.
7. Actualiza el estado en **Aplicaciones** conforme avanza (entrevista, oferta, rechazo), manteniendo todo el historial centralizado.

## 6. Extensiones futuras (fuera del MVP)
- Integración directa con Google Jobs API / scraping autorizado de LinkedIn-Indeed para búsqueda federada dentro de la app (no solo importación por URL).
- Exportación directa a PDF con plantillas ATS adicionales.
- Notificaciones/recordatorios de seguimiento de aplicaciones.
- App nativa (React Native) si la PWA resulta insuficiente en el uso real.
