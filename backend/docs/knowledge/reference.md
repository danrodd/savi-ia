# Referencia del schema — campo por campo

Este es el detalle de **qué campo va en cada entidad** y qué espera el sistema. Es la documentación de referencia para cuando editás un archivo y querés saber qué podés poner.

## Notación

- `requerido` — falla la validación si no está.
- `opcional` — puede omitirse. Por default es vacío o `null`.
- `enum` — solo valores específicos. Otros fallan.

## ModuleEntry — `data/modules/<slug>/overview.json`

Describe el módulo del ERP a alto nivel. Uno por carpeta de módulo.

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `code` | enum `ModuleCode` | ✅ | Código del módulo. Valores válidos: `CONTABILIDAD`, `NÓMINA` (con tilde), `INVENTARIO`, `CUENTACOBRAR`, `CUENTAPAGAR`, `CARTERAFINANCIERA`, `ACTIVOFIJO`, `CULTIVO`, `MANTENIMIENTO`, `VENTA`, `HERRAMIENTA`, `SEGURIDAD`, `TERCERO`, `EMPRESA`, `GENERAL`, `BÚSQUEDA`. |
| `label` | string | ✅ | Nombre humano. Ej.: "Contabilidad", "Cuentas por cobrar". |
| `purpose` | string | ✅ | 1-3 frases explicando qué hace el módulo. |
| `tags` | string[] | ⬜ | Etiquetas / palabras de búsqueda transversales. |
| `main_workflows` | string[] | ⬜ | IDs de los workflows centrales del módulo. |
| `main_forms` | string[] | ⬜ | Nombres internos de los formularios más representativos. |

**Ejemplo:**

```json
{
  "code": "CONTABILIDAD",
  "label": "Contabilidad",
  "purpose": "Libro contable, PUC, comprobantes y reportes financieros oficiales (Balance, P&G, exógenas DIAN).",
  "tags": ["PUC", "LibroDiario", "BalanceGeneral", "DIAN"],
  "main_workflows": ["wf_cierre_contable"],
  "main_forms": ["frmConsultaSaldoContable", "frmInformeBalanceGeneral", "frmCierreMes"]
}
```

---

## FormEntry — `data/modules/<slug>/forms/<frmXxx>.json`

La entidad más rica. Un archivo por formulario del ERP. Casi todos los campos son opcionales y se enriquecen gradualmente.

### Campos requeridos (lo mínimo para que un form sea válido)

| Campo | Tipo | Descripción |
|---|---|---|
| `name` | string | Identificador interno (`frmConciliacionBancaria`). **NO se le muestra al usuario.** |
| `module` | enum `ModuleCode` | A qué módulo pertenece. |
| `type` | enum `FormType` | `CRUD`, `CONSULTA`, `INFORME`, `PROCESO`, o `TRANSACCION`. |
| `description` | string | Resumen ejecutivo en 1-3 frases. |

### Campos opcionales — lo que el usuario VE

| Campo | Tipo | Descripción |
|---|---|---|
| `user_label` | string | Nombre humano. Ej.: "Conciliación bancaria". Si está vacío, el LLM usa el `name` sin el prefijo `frm`. |

### Campos opcionales — matching de intención

| Campo | Tipo | Descripción |
|---|---|---|
| `synonyms` | string[] | Frases como las diría un usuario. Ej.: `["conciliar banco", "cuadrar extracto", "cruzar banco contabilidad"]`. |
| `keywords` | string[] | Palabras técnicas/negocio sueltas. Ej.: `["conciliacion", "extracto", "banco"]`. |

> **Diferencia importante**: `synonyms` son frases; `keywords` son palabras sueltas. Las dos suman al score de búsqueda.

### Campos opcionales — navegación y procedimiento

| Campo | Tipo | Descripción |
|---|---|---|
| `navigation_path` | string[] | Ruta del menú principal. Ej.: `["Contabilidad", "Procesos", "Conciliación bancaria"]`. |
| `prerequisites` | string[] | Qué debe estar listo antes de usarlo. Ej.: `["Cuenta bancaria creada en el PUC", "Movimientos del período mayorizados"]`. |
| `how_to` | `HowToStep[]` | Pasos ordenados. Ver schema abajo. |

**`HowToStep`:**
```json
{ "step": 1, "action": "Seleccionar cuenta bancaria", "detail": "Si tiene varias, elegir la del extracto" }
```
- `step` (int, ≥1, requerido)
- `action` (string, requerido)
- `detail` (string, opcional — para aclaraciones)

### Campos opcionales — operaciones y reglas

| Campo | Tipo | Descripción |
|---|---|---|
| `actions` | string[] | Botones / verbos disponibles. Ej.: `["Importar extracto", "Cruzar automático", "Generar documento"]`. |
| `filters` | string[] | Filtros de búsqueda. Ej.: `["cuenta bancaria", "período", "estado conciliación"]`. |
| `business_rules` | string[] | Reglas duras del negocio. Ej.: `["Una partida marcada conciliada no se puede editar", "El saldo conciliado debe coincidir con el saldo mayorizado"]`. |

### Campos opcionales — cálculos y salidas

| Campo | Tipo | Descripción |
|---|---|---|
| `calculations` | `Calculation[]` | Fórmulas que aplican. Ver schema abajo. |
| `outputs` | string[] | Qué produce el formulario. Ej.: `["Documento de conciliación", "Listado de diferencias"]`. |

**`Calculation`:**
```json
{
  "name": "Saldo conciliado",
  "formula": "Saldo extracto - Cheques en tránsito + Depósitos en tránsito",
  "explanation": "Debe coincidir con el saldo contable del período."
}
```

### Campos opcionales — soporte

| Campo | Tipo | Descripción |
|---|---|---|
| `common_issues` | `CommonIssue[]` | Problemas frecuentes + solución. |

**`CommonIssue`:**
```json
{
  "problem": "El extracto no se importa",
  "solution": "Verificar formato OFX/CSV/Excel y que la cuenta exista en el PUC."
}
```

### Campos opcionales — cross-references

| Campo | Tipo | Descripción |
|---|---|---|
| `related_forms` | string[] | Otros formularios que se conectan. Ej.: `["frmPlanContable", "frmMovimientoContable"]`. |
| `related_workflows` | string[] | Workflows en los que participa. |
| `db_tables` | string[] | Tablas de la BD que toca. Solo referencia técnica. **No se le muestra al usuario.** |

### Campos opcionales — metadata

| Campo | Tipo | Descripción |
|---|---|---|
| `source` | string | De dónde viene esta info. Ej.: `"Manual oficial SEO ERP v2.5"`. |
| `updated` | string | Fecha YYYY-MM-DD de última revisión. |

### Ejemplo completo (un formulario rico)

```json
{
  "name": "frmConciliacionBancaria",
  "module": "CONTABILIDAD",
  "type": "PROCESO",
  "user_label": "Conciliación bancaria",
  "description": "Cruza el extracto bancario con la contabilidad del período.",
  "synonyms": ["conciliar banco", "cuadrar extracto", "cruzar banco contabilidad"],
  "keywords": ["conciliacion", "extracto", "banco", "cruce"],
  "navigation_path": ["Contabilidad", "Procesos", "Conciliación bancaria"],
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
    }
  ],
  "related_forms": ["frmPlanContable", "frmMovimientoContable", "frmInformeAuxiliar"],
  "related_workflows": ["wf_cierre_contable"],
  "db_tables": ["Contabilidad.ConciliacionBancaria", "Contabilidad.MovimientoContable"],
  "source": "Manual oficial SEO ERP v2.5",
  "updated": "2026-06-03"
}
```

### Ejemplo mínimo (lo que viene del v2)

```json
{
  "name": "frmConciliacionBancaria",
  "module": "CONTABILIDAD",
  "type": "PROCESO",
  "description": "Conciliación de extractos bancarios con la contabilidad.",
  "keywords": ["conciliacion bancaria", "extracto bancario"],
  "source": "sisfec_knowledge_base v2"
}
```

Los dos son válidos. El mínimo se enriquece con el tiempo.

---

## WorkflowEntry — `data/modules/<slug>/workflows/<id>.json`

Procesos end-to-end que cruzan formularios.

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `id` | string | ✅ | Identificador único. Convención: `wf_<concepto>`. Ej.: `wf_ciclo_venta`. |
| `name` | string | ✅ | Nombre humano. Ej.: "Ciclo de venta completo". |
| `description` | string | ✅ | Resumen del proceso. |
| `modules` | `ModuleCode[]` | ⬜ | Módulos involucrados en el workflow. |
| `synonyms` | string[] | ⬜ | Frases del usuario que lo describen. |
| `steps` | `WorkflowStep[]` | ✅ (mín 1) | Pasos ordenados. |

**`WorkflowStep`:**
```json
{
  "step": 1,
  "form": "frmCotizacion",
  "action": "Cotizar al cliente",
  "optional": true,
  "detail": "Si el cliente solicita cotización formal antes de pedir"
}
```
- `step` (int, ≥1, requerido)
- `form` (string, requerido — nombre interno del formulario que ejecuta el paso)
- `action` (string, requerido — qué hace el usuario)
- `optional` (bool, default `false`)
- `detail` (string, opcional)

### Ejemplo

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
    { "step": 3, "form": "frmFactura", "action": "Facturar", "optional": false },
    { "step": 4, "form": "frmEnvioFacturaElectronica", "action": "Enviar a DIAN", "optional": false },
    { "step": 5, "form": "frmReciboCliente", "action": "Recibir pago", "optional": false }
  ]
}
```

---

## FaqEntry — `data/modules/<slug>/faqs/<id>.json` o `data/shared/faqs/<id>.json`

Atajos para preguntas muy frecuentes que justifican respuesta canónica.

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `id` | string | ✅ | Identificador único. Convención: `faq_<descripcion>` o `faq_<NNN>`. |
| `question` | string | ✅ | La pregunta canónica. |
| `synonyms` | string[] | ⬜ | Otras formas de hacer la pregunta. |
| `module` | enum `ModuleCode` o `null` | ⬜ | A qué módulo aplica. `null` = transversal, visible para todos. |
| `answer_summary` | string | ✅ | Respuesta breve directa. |
| `related_forms` | string[] | ⬜ | Formularios que ayudan a responder más en detalle. |
| `related_workflows` | string[] | ⬜ | Workflows asociados. |

### Ejemplo

```json
{
  "id": "faq_consultar_saldos_contables",
  "question": "¿Qué formulario uso para consultar saldos contables?",
  "synonyms": ["ver saldo contable", "saldo de una cuenta", "consulta de saldos"],
  "module": "CONTABILIDAD",
  "answer_summary": "Andá a Contabilidad → Consultas → Saldos contables. Filtrás por año, mes y rango de cuentas del PUC.",
  "related_forms": ["frmConsultaSaldoContable"],
  "related_workflows": []
}
```

---

## GlossaryEntry — entradas dentro de `data/shared/glossary.json`

Definiciones de siglas y términos del dominio. El glosario es un solo archivo con una lista (no archivo por entrada).

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `term` | string | ✅ | Sigla o término (case-insensitive en búsqueda). |
| `definition` | string | ✅ | Qué significa. |
| `aliases` | string[] | ⬜ | Otras formas de escribirlo. |

### Ejemplo (el archivo entero es una lista)

```json
[
  {
    "term": "DIAN",
    "definition": "Dirección de Impuestos y Aduanas Nacionales — autoridad fiscal de Colombia.",
    "aliases": ["dian"]
  },
  {
    "term": "PILA",
    "definition": "Planilla Integrada de Liquidación de Aportes — formato oficial de seguridad social.",
    "aliases": ["pila", "planilla pila"]
  }
]
```

---

## Validaciones automáticas — qué falla al boot

Si **cualquier** archivo tiene problemas, el backend NO arranca. El error te dice exactamente cuál archivo y qué falla. Tipos de error:

- **JSON inválido**: comma de más, comilla sin cerrar.
- **Campo requerido faltante** (ej. `description` en un form): "Field required" en el error.
- **Tipo equivocado** (ej. `keywords: "string"` en vez de `["array", "of", "strings"]`).
- **Enum inválido** (ej. `module: "CONTABILDIAD"` con typo).
- **Campo extra no declarado** (ej. `descriptionn` por typo): `extra="forbid"` lo atrapa.

Esto es **a propósito**: preferimos crashear que servir respuestas con knowledge corrupto.
