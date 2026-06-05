# Sistema de conocimiento de SAVI

Este documento describe **cómo SAVI conoce el ERP**: qué módulos existen, qué hace cada formulario, cuáles son los procesos de negocio, cómo se navega hasta cada pantalla. Es la base sobre la que SAVI responde preguntas del tipo *"¿cómo facturo a un cliente?"* o *"necesito conciliar el extracto del banco, ¿qué hago?"*.

> **Resumen ejecutivo**: arquitectura híbrida en tres capas. Capa 1 — catálogo estructurado (lookup determinístico) sobre formularios, workflows, FAQs y glosario. Capa 2 — RAG semántico sobre manuales largos. Capa 3 — multi-tenant para conocimiento del cliente. Este doc cubre **Capa 1**, que es lo primero a implementar.

---

## 1. El problema que resolvemos

Hoy SAVI sabe consultar la BD del ERP (vía `consultar_datos` + `consultar_libre`), pero **no sabe explicar el ERP**. Si un usuario pregunta:

> *"Tengo que cuadrar el extracto del banco con la contabilidad, ¿cómo lo hago?"*

SAVI hoy:
- No tiene noción de qué formulario hace eso.
- Inventa pasos o se queda corto.
- No puede decir "andá a Contabilidad → Procesos → Conciliación".

Lo que necesitamos: que el LLM pueda **inferir la intención del usuario**, encontrar el concepto del ERP que la cubre (formulario, proceso, workflow) y responder con la ruta de navegación, los pasos, los cálculos involucrados y los formularios relacionados — todo en castellano natural.

Tenemos un punto de partida: el archivo `sisfec_knowledge_base_v2.json` (1232 líneas) ya tiene módulos, formularios, descripciones, keywords, workflows y un FAQ map. Es estructurado y curado por el director de desarrollo. Es el insumo principal de Capa 1.

## 2. Tres capas, propósitos distintos

```
┌────────────────────────────────────────────────────────────────┐
│ Capa 1 — Catálogo estructurado (este doc)                      │
│ Lookup determinístico sobre conceptos del ERP: formularios,    │
│ workflows, FAQs, glosario. Archivos JSON versionados en repo.  │
│ El LLM lo consulta vía tools.                                  │
└────────────────────────────────────────────────────────────────┘
                            │
┌────────────────────────────────────────────────────────────────┐
│ Capa 2 — RAG semántico (futuro)                                │
│ Manuales largos, capacitaciones, procedimientos detallados.    │
│ Markdown con frontmatter + pgvector + tsvector. Tool           │
│ search_knowledge(query, k).                                    │
└────────────────────────────────────────────────────────────────┘
                            │
┌────────────────────────────────────────────────────────────────┐
│ Capa 3 — Multi-tenant (futuro)                                 │
│ Conocimiento propio del cliente: políticas internas,           │
│ instructivos. tenant_id NULL para conocimiento global SAVI,    │
│ non-null para conocimiento del cliente actual.                 │
└────────────────────────────────────────────────────────────────┘
```

Las tres son complementarias:
- Capa 1 es lookup exacto y rápido — el LLM la usa cuando reconoce un concepto del ERP.
- Capa 2 entra cuando la pregunta es ambigua, conceptual o no matchea un formulario específico.
- Capa 3 capa lo idiosincrático de cada cliente.

Este doc cubre **solo Capa 1**. Las otras dos se documentarán cuando se implementen.

## 3. Distinción crítica vs `data_query` semantic layer

SAVI ya tiene un semantic layer en `app/modules/data_query/infrastructure/catalog/` con entidades como `productos`, `ventas`, `cartera`. **Ese es otro sistema distinto**:

| Sistema | Propósito | Granularidad | Salida |
|---|---|---|---|
| `data_query` (existente) | Traducir intención → SQL → datos | Tabla/entidad del ERP | Filas de la BD |
| `knowledge` (este doc) | Explicar conceptos del ERP | Formulario / workflow / FAQ | Texto / explicación |

Las dos se complementan:
- *"¿cómo cobro a un cliente?"* → knowledge responde "usá `frmReciboCliente`, ciclo Cartera..."
- *"¿cuánto me debe Juan?"* → data_query devuelve el saldo real consultando la BD.

No se pisan, no se confunden, y cuando una pregunta tiene ambas dimensiones el LLM las orquesta llamando primero al knowledge para entender el contexto y luego a data_query para los números.

## 4. Cómo lo usa el LLM en la práctica

El usuario **nunca** pregunta por nombre de formulario. El identificador `frmConciliacionBancaria` es interno y SAVI no debe mencionarlo nunca al usuario final (regla ya establecida en `CLAUDE.md`).

El flujo real:

```
Usuario: "Necesito conciliar el extracto del banco con la contabilidad."
   │
   ▼
LLM llama buscar_por_intencion("conciliar extracto banco contabilidad")
   │
   ▼
Catálogo matchea por keywords, descripción y tags → devuelve la entrada
COMPLETA del concepto correspondiente (su frmConciliacionBancaria) con
TODOS sus campos enriquecidos: descripción, ruta de menú, pasos,
cálculos, prerrequisitos, formularios relacionados.
   │
   ▼
LLM compone respuesta en castellano natural usando esos campos.
NUNCA menciona "frmConciliacionBancaria" — habla de "Conciliación
bancaria" o "el proceso de conciliación".
```

La respuesta típica del LLM:

> Para conciliar el extracto del banco con la contabilidad, andá a **Contabilidad → Procesos → Conciliación bancaria**.
>
> Antes de empezar necesitás:
> - La cuenta bancaria configurada en el plan contable.
> - Los movimientos contables del período ya mayorizados.
> - El extracto del banco en formato OFX, CSV o Excel.
>
> El proceso es: (1) seleccionás la cuenta bancaria, (2) importás el extracto, (3) el sistema cruza automáticamente por valor y referencia, (4) marcás manualmente las partidas que no cruzó solo, (5) generás el documento de conciliación.
>
> El saldo conciliado se calcula como: *Saldo del extracto − Cheques en tránsito + Depósitos en tránsito*, y tiene que coincidir con el saldo contable del período.

Esto es lo que distingue una respuesta útil de una respuesta de manual escolar.

## 5. Modelo de datos

Cuatro tipos de entidad principales:

### 5.1 — Module (módulo del ERP)

Dossier por módulo. Coincide 1:1 con los códigos de `ModuleCode` del sistema de autorización (CONTABILIDAD, NOMINA, INVENTARIO, etc.).

```json
{
  "code": "CONTABILIDAD",
  "label": "Contabilidad",
  "purpose": "Gestión del libro contable, plan único de cuentas, comprobantes y reportes financieros oficiales.",
  "tags": ["PUC", "LibroDiario", "BalanceGeneral", "EstadoResultados", "DIAN"],
  "main_workflows": ["wf_cierre_contable"],
  "main_forms": ["frmConsultaSaldoContable", "frmInformeBalanceGeneral"]
}
```

### 5.2 — Form (formulario del ERP)

La entidad más rica y la que más se consulta. Cada formulario es un archivo.

```json
{
  "name": "frmConciliacionBancaria",
  "module": "CONTABILIDAD",
  "type": "PROCESO",

  "user_label": "Conciliación bancaria",
  "synonyms": ["conciliar banco", "cuadrar extracto", "cruzar banco contabilidad"],
  "keywords": ["conciliacion", "extracto", "banco", "cruce"],

  "description": "Resumen ejecutivo en una frase: cruza el extracto bancario con la contabilidad del período.",

  "navigation_path": [
    "Menú principal",
    "Contabilidad",
    "Procesos",
    "Conciliación bancaria"
  ],

  "prerequisites": [
    "Cuenta bancaria creada en el plan contable",
    "Movimientos del período mayorizados",
    "Extracto del banco en formato OFX, CSV o Excel"
  ],

  "how_to": [
    { "step": 1, "action": "Seleccionar cuenta bancaria a conciliar" },
    { "step": 2, "action": "Importar extracto", "detail": "El sistema acepta OFX, CSV o Excel." },
    { "step": 3, "action": "Revisar cruces automáticos por valor y referencia" },
    { "step": 4, "action": "Marcar partidas conciliatorias manuales" },
    { "step": 5, "action": "Generar documento de conciliación" }
  ],

  "actions": ["Importar extracto", "Cruzar automático", "Marcar manual", "Generar documento"],

  "filters": ["cuenta bancaria", "período", "estado conciliación"],

  "business_rules": [
    "Solo se concilia un período por vez",
    "Una partida marcada conciliada no se puede editar — hay que revertir la conciliación primero",
    "El saldo conciliado debe coincidir con el saldo contable mayorizado"
  ],

  "calculations": [
    {
      "name": "Saldo conciliado",
      "formula": "Saldo extracto - Cheques en tránsito + Depósitos en tránsito",
      "explanation": "Debe coincidir con el saldo contable del período."
    }
  ],

  "outputs": [
    "Documento de conciliación con partidas cruzadas",
    "Listado de diferencias pendientes",
    "Asientos de ajuste automáticos cuando aplica"
  ],

  "common_issues": [
    {
      "problem": "El extracto no se importa",
      "solution": "Verificar formato (OFX, CSV o Excel) y que la cuenta bancaria exista en el plan contable."
    },
    {
      "problem": "El saldo conciliado no coincide",
      "solution": "Revisar partidas en tránsito (cheques no cobrados, depósitos pendientes) y mayorización del período."
    }
  ],

  "related_forms": ["frmPlanContable", "frmMovimientoContable", "frmInformeAuxiliar"],
  "related_workflows": ["wf_cierre_contable"],

  "db_tables": ["Contabilidad.ConciliacionBancaria", "Contabilidad.MovimientoContable"],

  "audience": ["funcional", "tecnico"],
  "source": "Manual oficial SEO ERP v2.5 + KB v2",
  "updated": "2026-06-03"
}
```

Casi todos los campos son **opcionales**. Un form puede empezar solo con `name`, `module`, `type`, `description`, `keywords`. Se enriquece gradualmente con `navigation_path`, `how_to`, `calculations`, etc., a medida que el equipo documenta más.

### 5.3 — Workflow (proceso de negocio end-to-end)

Cruza varios formularios. Lo equivalente a los `business_workflows` del JSON v2.

```json
{
  "id": "wf_ciclo_venta",
  "name": "Ciclo de venta completo",
  "description": "Flujo desde la cotización hasta el cobro del cliente.",
  "modules": ["CUENTACOBRAR", "CARTERAFINANCIERA", "VENTA"],
  "synonyms": ["proceso de venta", "vender a cliente", "ciclo comercial"],
  "steps": [
    { "step": 1, "form": "frmCotizacion", "action": "Cotizar", "optional": true },
    { "step": 2, "form": "frmPedido", "action": "Tomar pedido", "optional": true },
    { "step": 3, "form": "frmColaAlistamiento", "action": "Alistar pedido", "optional": true },
    { "step": 4, "form": "frmRemision", "action": "Despachar mercancía", "optional": true },
    { "step": 5, "form": "frmFactura", "action": "Facturar", "optional": false },
    { "step": 6, "form": "frmEnvioFacturaElectronica", "action": "Enviar a DIAN", "optional": false },
    { "step": 7, "form": "frmReciboCliente", "action": "Recibir pago", "optional": false }
  ]
}
```

### 5.4 — FAQ (pregunta natural pre-mapeada)

Atajos para preguntas muy comunes que justifican respuesta directa sin búsqueda.

```json
{
  "id": "faq_consultar_saldos_contables",
  "question": "¿Qué formulario uso para consultar saldos contables?",
  "synonyms": ["ver saldo contable", "saldo de una cuenta", "consulta de saldos"],
  "module": "CONTABILIDAD",
  "answer_summary": "Para consultar saldos contables andá a Contabilidad → Consultas → Saldos contables.",
  "related_forms": ["frmConsultaSaldoContable"],
  "related_workflows": []
}
```

### 5.5 — Shared (glosario y catálogos transversales)

```json
// shared/glossary.json
{
  "DIAN": "Dirección de Impuestos y Aduanas Nacionales — autoridad fiscal de Colombia.",
  "PILA": "Planilla Integrada de Liquidación de Aportes — formato oficial de seguridad social.",
  "NIT": "Número de Identificación Tributaria del contribuyente.",
  "PUC": "Plan Único de Cuentas — catálogo contable obligatorio."
}

// shared/form_types.json
{
  "CRUD": "Crear, Leer, Actualizar y Eliminar registros maestros.",
  "CONSULTA": "Visualizar información en grillas con filtros, sin modificar.",
  "INFORME": "Generar reporte imprimible o exportable.",
  "PROCESO": "Ejecutar operación de negocio (liquidación, cierre, envío)."
}
```

## 6. Organización en disco

```
backend/app/modules/knowledge/data/
├── modules/
│   ├── contabilidad/
│   │   ├── overview.json
│   │   ├── forms/
│   │   │   ├── frmConciliacionBancaria.json
│   │   │   ├── frmConsultaSaldoContable.json
│   │   │   └── ...
│   │   ├── workflows/
│   │   │   └── wf_cierre_contable.json
│   │   └── faqs/
│   │       └── faq_consultar_saldos.json
│   ├── inventario/
│   ├── nomina/
│   └── ...
└── shared/
    ├── glossary.json
    └── form_types.json
```

Por qué descompuesto en archivos chicos en vez de un único mega-JSON:

- Editar un formulario no requiere abrir 1232 líneas.
- Diff legible en code review (importante para conocimiento curado).
- Agregar nuevo concepto = nuevo archivo, no toca lo existente.
- Sin merge conflicts cuando dos personas documentan formularios distintos.
- El loader recompone todo al startup.

## 7. Carga y validación

Al boot del backend:

1. `StaticKnowledgeCatalog` recorre `data/` recursivamente.
2. Cada archivo se valida con **Pydantic** contra su entidad correspondiente.
3. Si un archivo es inválido, **el boot falla fuerte** con error explícito — no se arranca con catálogo corrupto.
4. Se construyen índices en memoria: por código de formulario, por módulo, por keyword, por sinónimo.
5. El catálogo queda como singleton inyectable a las tools y al system prompt.

Validación Pydantic significa:
- Fin del frontmatter custom-regex tipo `aniro-QA`.
- Si alguien escribe `module: "CONTABILDIAD"` (typo), el loader lo rechaza con error claro.
- Refactors del schema son rastreables y los tests detectan archivos rotos.

## 8. Tools que ve el LLM

| Tool | Propósito | Cuándo la usa el LLM |
|---|---|---|
| `buscar_por_intencion(query)` | Match natural → mejores 1-3 conceptos relevantes | Por defecto en cualquier pregunta de "cómo se hace X" |
| `listar_modulos_accesibles()` | Mostrar los módulos del usuario actual | "¿qué puedo hacer en SAVI?" |
| `describir_modulo(code)` | Overview de un módulo | "contame qué hace contabilidad" |
| `obtener_formulario_por_nombre(name)` | Lookup directo cuando ya se identificó | Uso interno, segundo paso después de buscar |
| `obtener_workflow(id)` | Detalle de un proceso end-to-end | "¿cuál es el ciclo de venta completo?" |
| `responder_faq(question)` | Atajo para preguntas con respuesta canónica | Preguntas muy frecuentes ya mapeadas |
| `traducir_termino(sigla)` | Glosario (DIAN, PILA, NIT, ...) | "¿qué es PILA?" |

**Todas filtran por los módulos del usuario actual.** Si el usuario solo tiene CONTABILIDAD y pregunta por algo de NÓMINA, las tools devuelven solo conceptos transversales o nada — el LLM le explica que no tiene acceso a Nómina.

## 9. Cómo se incorpora la información

### 9.1 — Bootstrap inicial desde el JSON v2

El JSON v2 actual (`sisfec_knowledge_base_v2.json`) **no se commitea como input al sistema**. Se procesa una vez con un script de migración que:

1. Lee el v2.
2. Genera la estructura de carpetas y archivos individuales.
3. Mapea `modules[].forms[]` → `data/modules/<lower>/forms/<name>.json`.
4. Mapea `business_workflows[]` → `data/modules/<modulo_principal>/workflows/`.
5. Mapea `question_to_form_map[]` → archivos `faqs/`.
6. Mapea el catálogo `form_type_catalog` → `shared/form_types.json`.

Después del bootstrap, **el JSON v2 queda como referencia histórica** pero la fuente de verdad pasa a ser la estructura de archivos.

### 9.2 — Editar información existente

1. Abrís el archivo del formulario o workflow correspondiente.
2. Modificás el campo (ej. agregar un `business_rule`, refinar el `description`).
3. PR + review + merge + deploy.
4. Próximo turno del chat tiene la info actualizada.

### 9.3 — Agregar un formulario o concepto nuevo

1. Creás el archivo nuevo siguiendo el schema.
2. El loader lo descubre automáticamente al próximo boot.
3. Sin registro central que modificar.

### 9.4 — Sumar información completamente nueva ("v3", "v4")

Aquí está la diferencia con el modelo de "JSON gigante versionado". En vez de hacer un v3 que reemplaza el v2, hay tres caminos:

**A) Agregar campos opcionales al schema existente** (más profundidad sin breaking):

Ejemplo: el equipo quiere documentar `troubleshooting` por formulario. Se agrega el campo a la entidad Pydantic como opcional. Los archivos viejos siguen válidos. Los nuevos pueden incluirlo. Sin migración.

**B) Agregar un tipo de entidad nuevo** (más amplitud):

Ejemplo: querés documentar **roles del ERP** (Contador, Cajero, Almacenista). Creás carpeta `data/roles/`, definís `RoleEntry` Pydantic, agregás tool `describir_rol(name)`. No toca nada existente.

**C) Cambio breaking del schema** (raro):

Si hay que cambiar tipo de un campo (ej. `description: str` → `description: dict[str, str]` por audiencia), se versiona el schema, el loader soporta ambas versiones, y los archivos viejos se migran de a uno con un script.

### 9.5 — Crecimiento esperado en el tiempo

```
Mes 1:  Bootstrap del v2     → ~110 forms + 4 workflows + 29 faqs.
Mes 2:  5 forms nuevos       → 5 archivos PR, no toca lo existente.
Mes 3:  Campo prerequisites  → schema +1 campo opcional, equipo enriquece de a poco.
Mes 6:  80 informes DIAN     → carpeta dossier por uno, PRs incrementales.
Mes 9:  Roles del ERP        → entidad nueva, carpeta nueva, tools nuevas.
Mes 12: Glosario DIAN x100   → shared/glossary.json crece con entradas.
```

En vez de "JSON v2 → v3 → v4" reemplazando todo, **siempre estás en la última versión coherente**, archivo por archivo, PR por PR.

## 10. Integración con módulos y autorización

Cada concepto (form, workflow, FAQ) declara los módulos a los que pertenece. La autorización funciona así:

- Si el concepto declara `module: CONTABILIDAD`, solo es visible a usuarios con CONTABILIDAD.
- Si declara `modules: [CONTABILIDAD, CUENTACOBRAR]`, requiere al menos uno.
- Sin declaración → conocimiento transversal, visible para todos los usuarios autenticados.
- El glosario y los `form_types` son transversales por naturaleza.

El filtrado se aplica en **cada tool** antes de devolver resultados al LLM. Si el LLM pregunta por algo prohibido, el catálogo retorna vacío (no error) — el LLM compone la respuesta de "no tenés acceso a ese módulo".

Esto se enchufa directo al sistema descrito en `authentication_system.md`: `current_user.modules` viaja al catálogo, el catálogo filtra.

## 11. Ventajas sobre alternativas evaluadas

| Alternativa | Por qué no |
|---|---|
| Un único `knowledge.json` versionado v2/v3/v4 | PRs ilegibles, merge conflicts garantizados, breaking changes costosos. |
| Hardcodear en system prompt | No escala. Sube tokens de cada turno. No filtrable por módulo. |
| Solo RAG semántico (embeddings) | Pierde precisión en lookups exactos (nombre de form, código DIAN). Caro y lento para preguntas simples. |
| YAML en vez de JSON | Pydantic soporta ambos. JSON tiene mejor tooling y menos sorpresas (YAML tiene cosas como `no` parseado como `False`). |
| Sin Pydantic, parseo manual | El parser custom de aniro-QA tiene bugs de edge cases (valores con `:`). Pydantic + jsonschema cubren todo. |
| Frontmatter en lugar de JSON puro | Para data estructurada (no prosa), el frontmatter es ceremonia innecesaria. Frontmatter sí en Capa 2 (manuales). |

## 12. Orden de implementación (Fase 1)

```
Paso 1 — Schema y dominio
  - Pydantic entities: ModuleEntry, FormEntry, WorkflowEntry, FaqEntry, GlossaryEntry
  - Tests de validación con fixtures

Paso 2 — Loader
  - StaticKnowledgeCatalog que recorre data/ y valida
  - Singleton inyectable
  - Tests de carga con catálogo mínimo

Paso 3 — Script de bootstrap
  - Lee sisfec_knowledge_base_v2.json
  - Genera la estructura de archivos
  - Reproducible, idempotente (re-correrlo no rompe trabajo manual posterior)

Paso 4 — Tools MCP
  - buscar_por_intencion, describir_modulo, obtener_formulario_por_nombre,
    obtener_workflow, responder_faq, traducir_termino, listar_modulos_accesibles
  - Filtro por módulos del usuario actual

Paso 5 — System prompt
  - Bloque que le dice al LLM: "tenés estas tools, usalas para responder
    preguntas sobre cómo usar el ERP, qué hace cada formulario,
    procesos de negocio"
  - Regla explícita: nunca mencionar nombres internos (frmXxx) al usuario

Paso 6 — Verificación E2E
  - Preguntas reales contra el chat: conciliación bancaria, facturar
    cliente, liquidar nómina, etc.
  - Validar que las respuestas son útiles, no mencionan nombres internos
    y respetan los módulos del usuario
```

## 13. Lo que queda fuera de Capa 1

Estos puntos son para Capas 2 y 3 — se documentarán cuando se implementen:

- **RAG semántico** sobre manuales largos.
- **Multi-tenant** con conocimiento del cliente.
- **UI admin** para subir docs sin pasar por git.
- **Versionado evolutivo** del schema con migraciones automáticas.
- **Sincronización con fuente externa** (si el equipo SEO mantiene su KB en otro sistema).

---

**Estado**: PROPUESTA APROBADA — pendiente de implementación.
