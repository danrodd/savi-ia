# Informe de avance: proveedores de IA

> Última actualización: 2026-09-14 · Versión `v1.1.0`

## Resumen

| Proveedor | Estado | Prueba real contra el ERP |
|---|---|---|
| Claude | Implementado, **activo** | ✅ verificado |
| Gemini | Implementado | ✅ verificado (key de pruebas hoy sin cuota) |
| OpenAI | Implementado, tests unitarios completos | ⏳ **pendiente**: no hay API key con saldo |

## Proveedores de IA

SAVI ahora soporta proveedores configurables de Claude, Gemini y OpenAI:

- Arquitectura desacoplada mediante adaptadores.
- Tools neutrales compartidas entre proveedores.
- Configuración persistente en la base de datos.
- Credenciales cifradas con Fernet.
- Activación de proveedor sin reiniciar la aplicación.
- Persistencia de proveedor y modelo por mensaje.
- Persistencia de tokens, uso y costo por proveedor.
- Manejo de proveedor no disponible en el chat.
- Diagnóstico de SAVI con proveedor y modelo activos.

## Gemini

- Integración mediante `google-genai`.
- Streaming y function calling.
- Soporte para `send`, `edit_last` y `regenerate`.
- Auto-títulos.
- Listado real de modelos desde la API.
- Búsqueda y recomendación automática de modelos.
- Configuración separada de modelo de chat y títulos.
- Retries para errores `429` y `503`.
- Backoff exponencial de `0.5s`, `1s` y `2s`.
- Fallback configurable a `gemini-3.1-flash-lite` y `gemini-flash-lite-latest`.
- Registro del modelo realmente utilizado y cálculo de costo según ese modelo.

## Claude

- Listado de modelos mediante la API directa de Anthropic.
- Soporte para `api_key` y `oauth_token`.
- Búsqueda y recomendación automática de modelos.
- Fallback manual para `local_session`, porque el CLI local no expone un catálogo.
- Prueba de credencial sin exigir modelos previamente seleccionados.

## OpenAI

Detalle en [`llm_providers/05-fase-openai.md`](llm_providers/05-fase-openai.md).

- Integración mediante el SDK oficial `openai` (fijado en `3.13.0`) y la
  **Responses API**, sin `store` ni `previous_response_id`: el historial
  sigue siendo de SAVI.
- Runner con loop manual de tools (las cuatro del ERP), streaming y
  preservación de los items de razonamiento entre vueltas, sin mostrarlos
  al usuario.
- Auto-títulos.
- Catálogo de modelos filtrado (excluye embeddings, imagen, audio, realtime y
  moderación, conserva IDs futuros) con recomendación de familias `gpt`/`o`.
- Validación del modelo elegido con una solicitud mínima antes de activarlo.
- Refusal y `response.failed` terminan en error, nunca en un mensaje vacío.
- Retries con backoff solo antes del primer token y fallback configurable
  (`OPENAI_FALLBACK_MODELS`).
- **Saldo agotado se distingue de límite temporal**: `insufficient_quota` no se
  reintenta y avisa que hay que cargar créditos.
- Diagnóstico del launcher prueba la conexión cuando OpenAI es el activo.

**Pendiente:** la prueba real con una API key con saldo (chat contra el ERP,
las cuatro tools, costo, E2E y bundle). La recarga mínima de OpenAI es USD 5.

## Versionado

La versión de la aplicación es el tag de git (ver
`installer/README.md#versionado`):

- `scripts/version.py` es la única fuente; `--proponer` y `--crear` calculan
  la siguiente versión desde los conventional commits.
- `build.ps1` la incrusta en frontend, backend e instalador.
- Visible en `GET /version`, `/health`, diagnóstico, login, sidebar del chat y
  menú de administración.
- Tags publicados: `v1.0.0`, `v1.0.1` y `v1.1.0` (integración de OpenAI).

## Interfaz administrativa

Se creó y mejoró `/admin/proveedores-ia` con:

- Configuración y prueba de credenciales.
- Listado y búsqueda de modelos.
- Recomendación automática de modelos generalistas.
- Configuración de precios por modelo.
- Activación de proveedor con confirmación explícita.
- Estados de proveedor: activo, configurado, sin configurar y credencial ilegible.
- Avisos cuando faltan precios o credenciales.

## Rediseño visual

Se renovaron las principales áreas de la aplicación:

- Login con mejor jerarquía, fondo, estados de error y responsive.
- Administración con navegación lateral, identidad visual y estados activos más claros.
- Chat con mejoras en sidebar, área de trabajo y estados vacíos.
- Tokens semánticos para temas claro y oscuro.
- Mejoras de focus, errores, superficies y responsive.

## Consumo

Se agregaron filtros reales por proveedor y modelo:

- Filtros para Claude, Gemini y OpenAI.
- Aplicación en backend sobre totales, series diarias, KPIs, usuarios y conversaciones.
- Filtrado en base de datos, no solo en frontend.
- Compatibilidad con el comportamiento anterior cuando no hay filtros.

## Pruebas

Estado al 2026-09-14 (`v1.1.0`):

Backend:

- Suite completa: `290 passed, 1 skipped`.
- Ruff correcto.
- Pyright estricto correcto.

Frontend:

- Type-check correcto.
- Build de producción correcto.
- Vitest: `48 passed`.
- E2E autenticado de administración y chat: `12 passed` en Chromium, Firefox y
  WebKit (corrida del 2026-09-14, antes de OpenAI; no se volvió a correr).

## Prueba real de Gemini

La API key proporcionada se validó directamente contra Gemini:

- Catálogo disponible: `41` modelos.
- Latencia del catálogo: aproximadamente `717–888 ms`.
- Gemini quedó configurado y activado en la base local.
- Modelo de chat: `gemini-3.6-flash`.
- Modelo de títulos: `gemini-3.6-flash`.
- La credencial quedó cifrada en la base de datos.
- Una pregunta fue respondida correctamente en aproximadamente `3.3 s`.
- Otra solicitud recibió `503 UNAVAILABLE` por alta demanda temporal.
- Se implementaron retries y fallback para mitigar este comportamiento.

La API key no se incluye en este informe, archivos ni commits.

## Commits principales

```text
b0d9530 refactor(chat): tools neutrales y puerto de titulo para varios proveedores
cd5c68b feat(llm): configurar proveedores de IA
afefd41 feat(gemini): integrar proveedor de IA
419a3f6 feat(llm-providers): fase 4 - interfaz admin, manejo de indisponibilidad y diagnostico multi-proveedor
eac668b feat(ui): mejorar proveedores y consumo
2973ba8 fix(gemini): mejorar resiliencia ante saturacion
2d1f499 feat(versioning): basar version en tags de git            (v1.0.0)
d620053 fix(installer): corregir compilacion de Inno Setup        (v1.0.1)
f009d3f docs(llm-providers): especificar integracion de OpenAI
ad23c50 feat(llm-providers): integrar proveedor OpenAI
827baab docs(llm-providers): endurecer contrato de errores y resiliencia de OpenAI
3e9ad8d fix(openai): manejar refusal y validar el modelo elegido
5bad293 fix(openai): distinguir saldo agotado de limite temporal
34749e8 feat(frontend): agregar iconos de proveedores y navegacion
```

## Seguimiento (2026-09-14)

- **`App.spec.ts` corregido.** Causa raíz real: Vitest 4 + jsdom 29 no
  exponen `window.localStorage` (queda `undefined`, no depende de la
  URL del entorno) — `authStore` y `permisosStore` lo usan al
  inicializarse, y cualquier componente que dispare esa carga revienta
  al montarse en un test. Se agregó `src/__tests__/setup.ts` (polyfill
  de `localStorage`/`sessionStorage` en memoria, registrado como
  `setupFiles` en `vitest.config.ts`) en vez de un mock puntual: cubre
  cualquier test futuro que monte algo que dependa de esos stores.
  Suite completa: `43 passed` en los `10` archivos de test.
- **Chat con Gemini verificado contra el ERP real** (`farmacias_similares`,
  proveedor activo `gemini-3.6-flash`, fallback automático a
  `gemini-3.1-flash-lite` observado en vivo):
  - `info_empresa`: razón social real (`FARMACIAS DE SIMILARES COLOMBIA SAS`).
  - `consultar_datos`: conteo agregado de terceros (19.866), coincide
    con la cifra ya verificada con Claude en una sesión anterior.
  - `consultar_libre`: manejo multi-turno de errores SQL reales
    (columna/valor inexistente), exploración de schema y respuesta
    correcta (54 usuarios activos).
  - `consultar_conocimiento` (dispatcher, 3 de sus 7 tipos): respuesta
    honesta de "no tengo información" ante un tema que efectivamente no
    está cargado — el catálogo de `knowledge/data` está vacío a
    propósito (pendiente #2/#3 de `CLAUDE.md`, fuera de este alcance).
  - `send` y `regenerate` completan bien; un `regenerate` cortado por un
    timeout del lado del cliente durante un reintento por saturación
    dejó el mensaje anterior `superseded` sin reemplazo — comportamiento
    esperado de cancelación de cliente a mitad de turno, no un bug.
- **E2E autenticado de administración y chat: escrito y verificado.**
  Nuevos `e2e/admin-llm-providers.spec.ts` y `e2e/chat.spec.ts` (más
  `e2e/helpers.ts` con login real y activación de proveedor por API),
  contra el backend real sin mocks:
  - Login real, listado de `/admin/proveedores-ia`, prueba de
    credencial de Claude con `local_session` (subprocess `claude.exe`
    real).
  - Chat: envío de un mensaje real y espera de la respuesta completa
    del asistente. El spec activa Claude (`local_session`) por API
    antes de correr — no depende de qué proveedor haya activo un
    administrador ni de la cuota de una API key externa.
  - `playwright.config.ts`: `workers` pasó a fijo en `1` (antes
    condicional a CI). Los specs autenticados comparten backend real
    (mismo usuario admin, proveedor de IA activo global, subprocess
    `claude.exe` único) — correrlos en paralelo producía timeouts
    espurios por contención real, no fallas del código.
  - Resultado: `4 passed` en Chromium, Firefox y WebKit (`12` en total).
- **Se detectó que la API key de Gemini usada en las pruebas ya está
  agotando cuota** (`429`/`503` en cascada, todos los reintentos
  fallando en un chat real durante esta sesión) — confirma que corresponde
  rotarla/eliminarla como ya estaba planeado.

- **Comparación empírica Claude vs. Gemini** — ver
  [`llm_providers/anexo-comparacion-claude-gemini.md`](llm_providers/anexo-comparacion-claude-gemini.md).
  Con las salvedades metodológicas ahí documentadas (Claude por
  `local_session`, Gemini con su modelo fallback por cuota agotada),
  ambos respondieron correcto; se detectó y corrigió una diferencia
  real de completitud (Claude agregaba el NIT a la razón social sin que
  se lo pidieran, Gemini no) agregando una regla de "completitud
  moderada" al system prompt **compartido** — no es un ajuste por
  proveedor. Verificación de la mejora con Gemini bloqueada: la key de
  pruebas dejó de responder del todo (150s sin respuesta, ni el
  fallback). Claude queda activo por decisión explícita del usuario.

## Pendientes

- **OpenAI con una API key con saldo** (recarga mínima USD 5): probe real,
  chat contra el ERP con las cuatro tools, costo, checklist E2E y turno desde el
  bundle. Orden detallado en `05-fase-openai.md` → "Estado de verificación".
- OpenAI: test de strict mode por tool antes de pasar a `strict=True`.
- Volver a correr el E2E en los tres navegadores después de la integración de
  OpenAI.
- Rotar o eliminar la API key de Gemini utilizada en las pruebas (ya
  agotando cuota, y hoy dejó de responder del todo); el usuario la
  eliminará directamente.
- Con una key nueva: verificar que la regla de "completitud moderada"
  del system prompt mejoró la respuesta de Gemini a "decime la razón
  social" (debería incluir el NIT, igual que Claude).
- Repetir la comparación de velocidad en igualdad de condiciones:
  Claude por `api_key` (no `local_session`), Gemini con el modelo
  principal (no el fallback) y, cuando haya key, OpenAI.
- Cargar el precio de los modelos de Gemini y OpenAI en
  `/admin/proveedores-ia` para que el costo se registre (sin precio,
  `cost_usd` queda `null`).
- Medir varias preguntas reales con tiempos y calidad de forma más
  sistemática (lo de hoy fue puntual, no un benchmark).
