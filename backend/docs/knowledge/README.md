# Sistema de conocimiento de SAVI — Índice

Acá vive **toda la documentación** del subsistema `app/modules/knowledge/`: el catálogo estructurado que le da a SAVI el conocimiento del ERP (módulos, formularios, workflows, FAQs, glosario).

## Qué leer según qué necesites hacer

| Si querés... | Leé |
|---|---|
| Entender de qué se trata todo esto (5 minutos) | [Quick start](#quick-start) más abajo |
| Conocer el porqué del diseño (3 capas, por qué híbrido) | [`architecture.md`](./architecture.md) |
| Editar el contenido de un formulario o sumar uno nuevo | [`editing-guide.md`](./editing-guide.md) ← **lo más importante para el equipo SEO** |
| Ver la referencia completa de cada campo del schema | [`reference.md`](./reference.md) |
| Agregar campos nuevos al schema o tipos de entidad nuevos | [`extending-guide.md`](./extending-guide.md) |
| Entender cómo el LLM usa el catálogo | [`tools-and-llm.md`](./tools-and-llm.md) |
| Diagnosticar un boot que falla, regenerar contenido desde el v2 | [`operations.md`](./operations.md) |

Y los dos documentos previos que aprobaste:

- [`backend/docs/knowledge_system.md`](../knowledge_system.md) — propuesta original (arquitectura, rationale, comparaciones)
- [`backend/docs/chat_data_access_proposal.md`](../chat_data_access_proposal.md) — propuesta de las 4 capas defensivas para acceso a datos del chat (futuro)

## Quick start

### ¿Qué es esto?

SAVI tiene que poder responder preguntas como *"necesito conciliar el extracto del banco, ¿cómo lo hago?"*. Para eso necesita **saber** qué hace cada formulario del ERP, qué pasos involucra, dónde está en el menú, qué prerrequisitos tiene.

Ese saber vive en archivos JSON en `app/modules/knowledge/data/`. El LLM los consulta vía 7 herramientas MCP (`buscar_por_intencion`, `describir_modulo`, etc.).

### Cómo está organizado

```
app/modules/knowledge/
├── domain/             # Entidades Pydantic (FormEntry, ModuleEntry, etc.)
├── infrastructure/     # Loader + singleton
└── data/               # ← El conocimiento real
    ├── modules/
    │   ├── contabilidad/
    │   │   ├── overview.json
    │   │   ├── forms/<frmXxx>.json
    │   │   ├── workflows/<wf_xxx>.json
    │   │   └── faqs/<faq_xxx>.json
    │   ├── inventario/
    │   ├── nomina/
    │   └── ...
    └── shared/
        └── glossary.json
```

Hay un archivo por concepto. Editar uno NO toca a los demás. Agregar uno nuevo NO requiere registrar en ningún lado: el loader lo descubre solo al boot.

### Cómo se modifica algo en 3 pasos

1. Abrís el archivo JSON correspondiente. Ejemplo: `data/modules/contabilidad/forms/frmConciliacionBancaria.json`.
2. Editás los campos que querés enriquecer (todos opcionales salvo `name`, `module`, `type`, `description`).
3. PR + reiniciar backend. **Si dejaste un campo inválido**, el backend falla al boot con un mensaje claro indicando el archivo y el error.

### Cómo se agrega un formulario nuevo

1. Creás `data/modules/<modulo>/forms/frmNuevo.json` siguiendo el schema (mínimo 4 campos).
2. PR + reiniciar backend.
3. Listo. Aparece automáticamente en `buscar_por_intencion` y en todos los listados del módulo.

### Cómo se agrega información completamente nueva

Lo cubrimos en detalle en [`extending-guide.md`](./extending-guide.md). Resumen rápido:
- **Nuevo campo en un schema existente** (ej. agregar `troubleshooting` a `FormEntry`): se agrega como opcional al Pydantic. Los archivos viejos siguen siendo válidos. Los nuevos pueden usarlo.
- **Nuevo tipo de entidad** (ej. `RoleEntry` para roles del ERP): nuevo archivo de dominio + extender el loader + nueva tool MCP.

### El principio de fondo

**El JSON v2 se descompuso en archivos chicos.** Nunca volvemos a un mega-JSON v3, v4, etc. Cada cambio es un PR que toca pocos archivos. El catálogo está siempre en su última versión coherente.

---

Si esto te dejó con preguntas, andá al doc específico de la tabla de arriba. Si todavía no te queda claro, decímelo en la próxima conversación y refinamos.
