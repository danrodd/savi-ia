# Por qué un turno tardaba 10 segundos en decir "ok"

> Fecha: 2026-09-15 · Estado: **implementado**, con medición antes y después.

Punto de partida: una pregunta cuya respuesta son **dos caracteres** tardaba
10,5 s. Eso no es el modelo pensando, es overhead. Este documento dice dónde
estaba y qué se hizo.

## Resultado

Mismo equipo, mismas preguntas, backend real.

| | Antes | Después |
|---|---|---|
| Turno mínimo — primer evento | 7,24 s | **2,52 s** |
| Turno mínimo — total | 10,48 s | **3,09 s** |
| Turno con tool del ERP — total | 17,63 s | **8,48 s** |
| 3 turnos simultáneos — total c/u | ~21,4 s | **4,4–5,7 s** |
| Cola después de `done` | 1,7–1,9 s | 0,55–0,62 s |

## Dónde estaba el tiempo

Lo primero fue partir el turno en fases para no optimizar a ciegas:

```
validaciones + apertura del SSE :  0,03 s   <- nada que hacer acá
primer evento (spawn + modelo)  :  8,51 s   <- todo el problema
cierre del stream               : +1,90 s   despues de `done`
```

### 1. El CLI cargaba la configuración del equipo

`claude --version` tarda **0,04 s**: el binario arranca al instante. Pero
`query()` tardaba 7-10 s, porque el CLI levanta una sesión completa de Claude
Code y lee el `~/.claude` de quien instaló SAVI: settings, plugins, hooks, MCP
servers y skills. En el equipo de desarrollo se veía en el log un hook personal
ejecutándose **dentro de un turno de SAVI**.

Medido con el runner real y el MCP de SAVI montado:

| Opciones | Turno simple | Turno con tool |
|---|---|---|
| Como estaba | 10,88 s | 18,04 s |
| `setting_sources=[]` | 4,26 s | 11,44 s |
| `+ strict_mcp_config=True` | **3,37 s** | **9,88 s** |

La tool (`mcp__savi__consultar_conocimiento`) se sigue invocando en los tres
casos, y `local_session` sigue autenticando: las credenciales no viven en los
setting sources.

Esto es tanto rendimiento como corrección. Es el mismo razonamiento que ya
justificaba `tools=[]` en el runner —lo que no se necesita, no se carga— con un
agregado: SAVI no puede comportarse distinto según lo que tenga configurado el
equipo donde corre, y un hook ajeno en el camino de una respuesta es código que
nadie revisó.

Vive en `ISOLATED_CLI_OPTIONS` (`app/infrastructure/claude_cli.py`) y se aplica
en los tres lugares que lanzan el CLI: el turno, el auto-título y la prueba de
credencial.

### 2. El cupo se retenía después de `done`

El stream quedaba abierto 1,7-3,4 s después del evento `done`, esperando el
auto-título de segunda fase. Como el cupo global se soltaba al terminar la
tarea, esos segundos eran capacidad retenida —de tres cupos— por algo
cosmético.

Ahora el cupo se suelta con `done` y el turno sigue vivo: el stream queda
abierto para emitir `title_update` y el candado por conversación no se toca. Se
libera solo el recurso escaso. `_liberar_cupo` es idempotente y `_cerrar` lo
llama igual, porque un turno que muere por error, cancelación o timeout nunca
llegó a emitir `done`.

## Lo que se midió y NO era el problema

Anotado para no volver a mirarlo:

- **API REST**: todo por debajo de 15 ms. `/health` 1 ms, `/conversations`
  9,6 ms, `/chat/activo` 4,6 ms.
- **Validaciones antes del SSE**: 0,03 s.
- **Base de datos**: los índices cubren los accesos
  (`ix_messages_conversation_created`, `ix_conversations_owner`,
  `ix_conversations_updated_at`).
- **Bundle del frontend**: entry de 185 KB; mermaid, cytoscape, xlsx y katex ya
  son chunks perezosos.
- **Concurrencia**: tres turnos simultáneos se degradan poco y el cuarto rebota
  con 429, como corresponde.

## Referencia: Gemini

Medido con el mismo turno mínimo, antes del arreglo: Gemini contestaba en
1,6-3,0 s contra los 6-10 s de Claude local. Esa brecha era el arranque del
CLI, no el modelo — con el aislamiento aplicado, Claude queda en 2,5-3,5 s.

## Queda pendiente

**Dos subprocesos por turno.** Contando `node.exe` durante un turno se ven dos:
el turno y el generador de títulos, que hace su propio `query()`. Con el
aislamiento cada uno cuesta ~3 s en lugar de ~10, pero sigue siendo una sesión
completa del CLI para producir cinco palabras. Opciones a evaluar: generar el
título solo en la primera fase, o titular siempre con un proveedor HTTP barato
sin importar cuál esté activo.
