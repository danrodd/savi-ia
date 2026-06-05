# Arquitectura del knowledge

Este documento explica **por qué** el sistema está diseñado como está, qué decisiones se tomaron y qué se descartó. Si solo querés saber cómo editar contenido, andá a [`editing-guide.md`](./editing-guide.md) — esto es para quien quiere entender el fondo.

> Hay un doc previo más extenso en [`backend/docs/knowledge_system.md`](../knowledge_system.md) con la propuesta original aprobada. Este resume y agrega la implementación real.

## 1. El problema que resolvemos

SAVI ya sabe consultar la BD del ERP (vía `data_query`), pero hasta ahora **no sabía explicar el ERP**. Un usuario que pregunta *"¿cómo facturo a un cliente?"* o *"necesito conciliar el extracto del banco"* recibía una respuesta inventada o vaga.

Lo que necesitábamos: un sistema donde el LLM pueda **inferir la intención del usuario**, encontrar el concepto del ERP que la cubre (formulario, proceso, workflow), y responder con:

- La ruta de navegación del menú.
- Los pasos del proceso.
- Los prerrequisitos.
- Los cálculos involucrados.
- Los problemas comunes.

Todo en castellano natural, sin mencionar nunca nombres internos como `frmFactura`.

## 2. La arquitectura — tres capas

```
┌───────────────────────────────────────────────────────────────┐
│ Capa 1 — Catálogo estructurado  (LO QUE ACABAMOS DE HACER)    │
│ Lookup determinístico sobre conceptos del ERP.                │
│ Archivos JSON versionados en repo.                            │
│ El LLM lo consulta vía 7 tools MCP.                           │
└───────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────────────────────────────────────────┐
│ Capa 2 — RAG semántico  (FUTURO)                              │
│ Manuales largos, capacitaciones. Markdown + pgvector +        │
│ tsvector. Tool search_knowledge(query, k).                    │
└───────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────────────────────────────────────────┐
│ Capa 3 — Multi-tenant  (FUTURO)                               │
│ Conocimiento propio del cliente: políticas, instructivos.     │
│ tenant_id NULL = global, non-null = del cliente.              │
└───────────────────────────────────────────────────────────────┘
```

Las tres capas son **complementarias**, no excluyentes. Capa 1 es lo que tenemos. Las otras dos se implementarán cuando la primera demuestre valor.

## 3. ¿Por qué híbrida en vez de "solo RAG"?

La tentación inicial era *"tirá todo a un vector store y listo"*. Lo descartamos porque:

| Caso | Catálogo (Capa 1) | RAG (Capa 2) |
|---|---|---|
| *"¿Cómo facturo a un cliente?"* | ✅ Lookup determinístico en FAQs/forms | ⚠️ Semántico, baja precisión |
| *"¿Cuál es el ciclo de venta?"* | ✅ Devuelve workflow estructurado completo | ⚠️ Chunked, pierde la secuencia |
| *"¿Cuáles son las reglas para el cierre contable?"* | ✅ business_rules estructurado | ⚠️ Puede mezclar reglas de otros formularios |
| *"¿Qué dice el manual sobre la NIIF 16?"* | ❌ Texto largo no es su shape | ✅ RAG semántico es lo ideal |
| *"¿Cuál es la política de descuentos del cliente?"* | ❌ No es info del ERP, es del cliente | ✅ Multi-tenant con docs del cliente |

La Capa 1 cubre todo lo que es **lookup directo** de info bien estructurada. Es el 80% de las preguntas típicas. La Capa 2 cubre las preguntas conceptuales y la narrativa larga. Forzar todo por RAG = baja precisión + sube latencia + sube costo.

## 4. ¿Cómo se diferencia esto del semantic layer `data_query`?

Pregunta importante porque hay confusión potencial.

| Sistema | Propósito | Granularidad | Salida |
|---|---|---|---|
| `data_query` (existente) | Traducir intención → SQL → datos | Tabla/entidad del ERP | Filas de la BD |
| `knowledge` (nuevo) | Explicar conceptos del ERP | Formulario / workflow / FAQ | Texto / explicación |

Ejemplo concreto:
- *"¿Cómo cobro a un cliente?"* → `knowledge` responde *"usá Recibo de Cliente, ciclo Cartera, cruzá la factura..."*.
- *"¿Cuánto me debe Juan?"* → `data_query` devuelve el saldo real consultando la BD.

Se complementan. Un mismo turno puede usar las dos (el LLM decide). No se pisan ni se confunden.

## 5. ¿Por qué archivos chicos y no un mega-JSON?

El JSON v2 que tenías era de **1232 líneas**. Editarlo significaba:
- PR ilegible (diffs enormes).
- Merge conflicts si dos personas tocaban a la vez.
- Re-leer todo para validar que no rompiste algo.

Lo descompusimos en **101 archivos** (uno por formulario), 4 archivos de workflow, 29 archivos de FAQ, 10 archivos de overview de módulo. Total: ~144 archivos chicos.

Ventajas:
- **Editar un form** = abrir 1 archivo de ~30 líneas.
- **Sumar un form** = crear 1 archivo nuevo. El loader lo descubre.
- **Diff legible en PR** = cambios concentrados.
- **Sin conflictos** = dos personas pueden editar dos forms distintos sin pisarse.
- **Schema único** = todos los forms validan contra el mismo Pydantic.

El costo: el loader recorre el árbol al boot. Eso es del orden de milisegundos para 150 archivos.

## 6. ¿Cómo nos integramos con el sistema de autorización?

Cada entidad del catálogo (form, workflow, FAQ, module) declara un `module: ModuleCode`. Cuando el LLM llama una tool del knowledge:

1. La ruta `/chat` resuelve `user.modules` del usuario autenticado.
2. Lo pasa al `ChatTurnUseCase` → `runner.stream_turn` → `build_savi_mcp_server`.
3. El server construye las tools con `allowed_modules` baked-in por clausura.
4. Cada tool filtra antes de devolver al LLM.

Si el usuario es admin (`is_admin=True`), `allowed_modules` viaja como `None` y las tools no filtran nada.

Si el usuario tiene solo CONTABILIDAD y pregunta por algo de NÓMINA, las tools devuelven listas vacías + un `message` explicativo. El LLM se lo traduce: *"no tenés acceso al módulo de Nómina, no puedo darte esa información"*.

## 7. ¿Por qué Pydantic y no JSON Schema o YAML?

| Opción | Por qué no |
|---|---|
| JSON Schema puro | Sin tipos en Python. Errores feos. Sin autocompletado. |
| YAML | Pydantic acepta dict, no importa el formato origen. JSON tiene mejor tooling y menos sorpresas (YAML interpreta `no` como `False`). |
| Parser custom | Lo hizo `aniro-QA` con regex y tiene bugs con valores que contienen `:`. Pydantic v2 + JSON estándar = cero ambigüedad. |
| Dataclasses | No validan al construir. No tienen `extra="forbid"` para detectar campos typos. |

Pydantic v2 nos da:
- Validación al boot (loud-fail si un archivo está roto).
- `extra="forbid"`: si alguien escribe `descrption` por `description`, falla con error claro.
- Tipos enum: si alguien pone `"CONTABILDIAD"` (typo), falla con error claro.
- Autocompletado en IDE para devs que tocan los archivos desde el editor.

## 8. Decisiones que dejamos para después

Estas son explícitas — no las implementamos hoy:

- **RAG sobre manuales largos** (Capa 2). Cuando los manuales del producto estén digitalizados y sean voluminosos.
- **Multi-tenant** (Capa 3). Cuando dos o más clientes quieran tener conocimiento propio sin pisarse.
- **UI admin para subir docs sin pasar por git**. Cuando la frecuencia de edición lo justifique.
- **Cache de la búsqueda por intención**. El scoring es O(n) sobre los 101 forms — perfectamente performante hoy. Si crece a miles, se piensa.
- **Sinónimos semánticos via embeddings**. El matching hoy es por keywords + sinónimos declarados. Si necesita más fineza, se enchufa un embedder a la búsqueda.

## 9. Costo aproximado (orden de magnitud)

- **Carga al boot**: ~50ms para 101 forms.
- **Memoria**: ~2 MB de JSON parseado.
- **Per-tool call**: O(n) en `buscar_por_intencion` con n=101 forms ≈ <1ms.
- **Per-turno**: el LLM llama 0, 1 o 2 tools. Sin I/O, sin DB, sin embeddings.

Es prácticamente gratis comparado con el costo del LLM mismo.

## 10. Quick mental model

> **El JSON v2 era una enciclopedia.** El knowledge catalog es esa misma enciclopedia descompuesta en fichas individuales, cada una validada por Pydantic, indexada en memoria, y consultable por el LLM via 7 tools que filtran por permisos del usuario.

Con eso en mente, los otros docs te cuentan la operatoria diaria.
