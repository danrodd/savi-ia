# Informe de avance: proveedores de IA

## Proveedores de IA

SAVI ahora soporta proveedores configurables de Claude y Gemini:

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

- Filtros para Claude y Gemini.
- Aplicación en backend sobre totales, series diarias, KPIs, usuarios y conversaciones.
- Filtrado en base de datos, no solo en frontend.
- Compatibilidad con el comportamiento anterior cuando no hay filtros.

## Pruebas

Backend:

- Suite completa: `247 passed, 1 skipped`.
- Tests específicos de proveedores: `34 passed`.
- Tests de resiliencia de Gemini: `12 passed`.
- Ruff correcto.
- Pyright estricto correcto.

Frontend:

- Type-check correcto.
- Build de producción correcto.
- E2E base aprobado en Chromium, Firefox y WebKit.
- Vitest: `42 passed` y una falla preexistente en `App.spec.ts` por montar la aplicación sin Pinia activa.

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
  [`llm_providers/05-comparacion-claude-gemini.md`](llm_providers/05-comparacion-claude-gemini.md).
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

- Rotar o eliminar la API key de Gemini utilizada en las pruebas (ya
  agotando cuota, y hoy dejó de responder del todo); el usuario la
  eliminará directamente.
- Con una key nueva: verificar que la regla de "completitud moderada"
  del system prompt mejoró la respuesta de Gemini a "decime la razón
  social" (debería incluir el NIT, igual que Claude).
- Repetir la comparación de velocidad en igualdad de condiciones:
  Claude por `api_key` (no `local_session`) y Gemini con el modelo
  principal (no el fallback).
- Cargar el precio de los modelos de Gemini en `/admin/proveedores-ia`
  para que el costo se registre (hoy `cost_usd` queda `null`).
- Medir varias preguntas reales con tiempos y calidad de forma más
  sistemática (lo de hoy fue puntual, no un benchmark).
