# Plan de remediación de seguridad y resistencia

> Origen: [`docs/revision-general.md`](../revision-general.md) (2026-09-15).
> Esto **no es un PRD**: no define producto nuevo. Es el plan para cerrar
> defectos ya identificados y verificados, con una spec por frente.
>
> Estado: **Fases 0 a 3 implementadas y verificadas** (2026-09-15); queda la 4.

## Qué resuelve

La revisión encontró 1 hallazgo crítico, 6 altos, 13 medios y 8 bajos. El plan
los agrupa en **cinco fases ordenadas por riesgo y por dependencia**, no por
módulo: cada fase deja la aplicación en un estado mejor que la anterior y se
puede cortar al final de cualquiera.

| Fase | Objetivo | Hallazgos | Esfuerzo | Bloquea a |
|---|---|---|---|---|
| [0 — Cierre urgente](01-fase-0-cierre-urgente.md) ✅ | Sacar la ejecución de código y las llaves del alcance del chat | C1, M2, M3, O3 | ~1 día | Cualquier despliegue |
| [1 — Datos del ERP](02-fase-1-datos-erp.md) ✅ | Que un usuario solo vea los datos que le corresponden | A1, A2, M4, M7 | ~3-4 días | Usuarios reales |
| [2 — Resistencia](03-fase-2-resistencia.md) ✅ | Que la app aguante abuso y concurrencia | O1, O2, O4, M5 | ~3 días | Usuarios reales |
| [3 — Multiempresa](04-fase-3-multiempresa.md) ✅ | Aislar clientes entre sí | A3, M1, O6 | ~3 días | SAVI Servidor |
| [4 — Deuda y pulido](05-fase-4-deuda-y-ux.md) | Calidad, costos visibles, UX | M6, M8, M9, O5, O7, bajas | ~4-5 días | — |

## Principios del plan

| Principio | Qué significa acá |
|---|---|
| **El modelo no es un control de seguridad** | Que Claude "se niegue" no cuenta. Todo límite se aplica en código, antes o después del modelo. |
| **Fallar cerrado** | Ante duda de permisos, negar. Ante falta de configuración crítica (secreto, tarifa), no arrancar o avisar, nunca seguir en silencio. |
| **Cada corrección trae su test** | Un hallazgo sin test de regresión se considera no cerrado. |
| **Sin romper la app de escritorio** | Es el despliegue actual y funciona. Los límites nuevos se configuran con defaults que un usuario único no nota. |
| **Medir antes y después** | C1 y O2 cambian el costo por respuesta; se mide con los scripts que ya existen. |

## Definición de terminado

Una fase está cerrada cuando:

- [ ] Todos sus hallazgos tienen corrección y test.
- [ ] `uv run pytest`, `uv run lint` y `uv run typecheck` en verde.
- [ ] El frontend, si cambió: `vitest`, `vue-tsc` y los E2E de Chromium en verde.
- [ ] La verificación manual descrita en la spec quedó registrada en su sección "Verificación".
- [ ] El hallazgo quedó marcado en el seguimiento de abajo.

## Seguimiento

| ID | Hallazgo | Fase | Estado |
|---|---|---|---|
| C1 | Claude con Bash, Read, Write y WebFetch sin permiso | 0 | **hecho** |
| M2 | `JWT_SECRET` por defecto aceptado | 0 | **hecho** |
| M3 | Dependencias con CVE | 0 | **hecho** |
| O3 | `/health` público golpea la BD | 0 | **hecho** |
| A1 | SQL libre sin permisos del ERP | 1 | **hecho** |
| A2 | Superusuario y funciones peligrosas | 1 | **hecho** |
| M4 | Fronteras de seguridad sin tests | 1 | **hecho** |
| M7 | Error de herramienta crudo al modelo | 1 | **hecho** |
| O1 | Sin rate limiting | 2 | **hecho** |
| O2 | Sin tope de turnos concurrentes | 2 | **hecho** |
| O4 | Turno sin timeout de pared | 2 | **hecho** |
| M5 | Turnos concurrentes en una conversación | 2 | **hecho** |
| A3 | Administrador de una base administra todas | 3 | **hecho** |
| M1 | Módulos calculados contra la base equivocada | 3 | **hecho** |
| O6 | SQLite con varios usuarios | 3 | **hecho** (queda acortar la transacción del turno) |
| M6 | Costo invisible sin tarifa | 4 | pendiente |
| M8 | Interfaz de documentos | 4 | pendiente |
| M9 | Tres runners duplicados | 4 | pendiente |
| O5 | Ingesta en serie | 4 | pendiente |
| O7 | Reuso de refresh token | 4 | pendiente |
| B1–B7 | Bajas | 4 | pendiente |

## Riesgos del propio plan

| Riesgo | Mitigación |
|---|---|
| Restringir el SQL libre rompe respuestas que hoy funcionan | Fase 1 arranca midiendo: se registra qué consultas reales quedarían fuera antes de activar el bloqueo. El auditor de `free_query` ya guarda el SQL de cada turno. |
| El rate limit molesta a un usuario legítimo | Defaults holgados y configurables; se calibran con los números de la Fase 2. |
| `tools=[]` cambia el comportamiento del agente | Hay E2E de chat con Claude que verifican una respuesta citada; se corren antes y después. |
| Cambiar el modelo de permisos exige decisión de producto | La Fase 1 presenta las tres opciones con su costo; la decisión se toma antes de escribir código. |

## Orden sugerido de ejecución

1. **Fase 0 completa** — es de horas y saca el riesgo más grave.
2. **Fase 2 antes que la 1** si se quiere abrir a usuarios rápido: el rate limit es más barato que el modelo de permisos y mitiga el abuso mientras se decide.
3. **Fase 1** con su decisión de producto tomada.
4. **Fase 3** solo cuando SAVI Servidor esté en la agenda.
5. **Fase 4** en paralelo, cuando haya holgura.
