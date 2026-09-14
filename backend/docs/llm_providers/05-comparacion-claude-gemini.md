# Comparación empírica: Claude vs. Gemini

> Parte de: [PRD — Proveedores de IA configurables](00-prd.md)
> Fecha: 2026-09-14 · Método: mismas 3 preguntas, contra el ERP real
> (`farmacias_similares`), conversaciones nuevas por pregunta, sin
> ninguna otra carga corriendo en simultáneo.

## Resultado esperado

- [x] Medir tiempo de respuesta de las mismas preguntas en ambos proveedores.
- [x] Juzgar calidad/completitud de las respuestas.
- [x] Identificar una brecha de calidad reproducible y corregirla en el
      system prompt compartido (no en un proveedor puntual).

## Metodología

Tres preguntas, cada una en una conversación nueva (sin contexto previo
que favorezca a la segunda tanda):

1. "Resumime en una frase muy corta qué es SAVI." — sin tools.
2. "Decime la razón social de la empresa." — tool `info_empresa`.
3. "Cuántos terceros (clientes o proveedores) tenemos registrados en
   total?" — tool `consultar_datos`, modo agregado.

**Salvedades metodológicas — no es una comparación 100% pareja**:

- Claude corrió con `credential_kind: local_session` (el CLI `claude`
  como subproceso), no con `api_key`. El subproceso agrega overhead de
  arranque que una llamada HTTP directa no tiene.
- La API key de Gemini usada en las pruebas ya estaba agotando cuota
  (ver `INFORME_AVANCE_PROVEEDORES_IA.md`): el modelo configurado
  (`gemini-3.6-flash`) devolvía `429`/`503` y el sistema caía al
  fallback (`gemini-3.1-flash-lite`) en casi todas las corridas. Los
  tiempos de Gemini son del modelo *fallback*, no del principal.

Con esas dos salvedades, la comparación no aísla "el modelo" — mezcla
modelo + transporte + estado de cuota. Sirve para una primera lectura,
no para una conclusión definitiva sobre qué proveedor es más rápido en
igualdad de condiciones.

## Resultados

### Tiempos (primera corrida, después de descartar una corrida contaminada por E2E corriendo en paralelo)

| Pregunta | Claude (`claude-sonnet-4-6`, local_session) | Gemini (`gemini-3.1-flash-lite`, api_key) |
|---|---|---|
| "¿Qué es SAVI?" | 19 s | 7 s |
| Razón social | 29 s | 16 s |
| Conteo de terceros | 44 s | 10 s |

### Costo

- Claude: `$0.031` / `$0.053` / `$0.100` (créditos de Anthropic).
- Gemini: no se registró (`cost_usd: null`) — falta cargar el precio de
  `gemini-3.1-flash-lite` en `/admin/proveedores-ia`. Pendiente aparte,
  no bloqueante.

### Calidad

Las dos respondieron correcto y sin alucinar las 3 preguntas (razón
social exacta, 19.866 terceros exacto — mismo número ya verificado con
Claude en una sesión anterior).

Diferencia real observada: ante "decime la razón social", Claude
agregó el NIT sin que se lo pidieran (dato que la tool `info_empresa`
sí trae, junto con dirección, teléfono, representante legal, etc.);
Gemini respondió solo la razón social, ciñéndose estrictamente a lo
pedido. No es que Gemini "sepa menos" — la tool le devuelve exactamente
los mismos campos a los dos; es una diferencia de iniciativa entre
modelos frente al mismo prompt.

## Ajuste aplicado

Se agregó una regla de **completitud moderada** en
`app/modules/chat/infrastructure/llm/system_prompt.py` (prompt
compartido por todos los proveedores, ver [Fase 1](01-fase-tools-neutrales.md)):
cuando el usuario pide un dato puntual de un registro que trae varios
campos relacionados en la misma respuesta de la tool, sumar 1-2 campos
que un colega daría por iniciativa propia (el NIT junto a la razón
social, el teléfono junto a un contacto) — sin listar el registro
completo, eso ya lo cubre la regla existente de "2-5 valores" que
aplica cuando el usuario pregunta por "los datos de" algo.

Es un cambio de prompt, no de código de un proveedor: la expectativa es
que ambos (y cualquier proveedor futuro) se vuelvan más consistentes
entre sí, en vez de depender del estilo natural de cada modelo.

## Verificación

- [x] Backend reiniciado para tomar el prompt nuevo (no hay `--reload`).
- [ ] Re-verificar la pregunta de razón social con Gemini tras el
      ajuste: **bloqueado**. El intento de verificación agotó `150s` sin
      respuesta (ni siquiera el fallback `gemini-3.1-flash-lite`
      contestó) — la API key de pruebas dejó de responder por completo
      durante esta sesión. Queda pendiente para cuando el usuario cargue
      una key nueva.

## Recomendación

No hay una conclusión firme de "cuál proveedor es más rápido" con esta
evidencia, por las salvedades metodológicas de arriba. Para una
comparación justa, repetir con:

- Claude por `api_key` (sin el overhead del subprocess CLI).
- Gemini con una key sin cuota agotada, para medir el modelo principal
  y no el fallback.

Mientras tanto, Claude queda como proveedor activo por decisión
explícita del usuario (2026-09-14).
