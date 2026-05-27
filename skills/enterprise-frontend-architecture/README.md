# enterprise-frontend-architecture

Skill personal/global que encapsula la arquitectura de referencia para frontends Vue 3 empresariales. Reemplaza la práctica de pegar el archivo de Obsidian `Referencia de Frontend Empresarial.md` en cada conversación.

## ¿Cuándo se dispara?

Carga automáticamente cuando el contexto incluye señales como:

- "Vue 3 enterprise frontend", "feature-based modules"
- `vue-query`, Pinia setup, `shadcn-vue`, axios `HttpClient`
- Arrancar un proyecto nuevo con el stack de referencia
- Auditar un módulo existente contra las reglas estrictas (encapsulamiento, DTO ≠ Modelo, caché centralizada, tiempo real unidireccional)

Si no se dispara sola, invocarla con `/enterprise-frontend-architecture` o pedirla por nombre.

## Estructura

```
enterprise-frontend-architecture/
├── SKILL.md                 # Contrato corto (<700 tokens) — Hard Rules, Decision Gates
├── README.md                # Este archivo (no se carga al contexto del LLM)
├── assets/
│   └── starter-kit.sh       # Comandos pnpm para bootstrap
└── references/
    ├── stack.md             # Versiones y runtime
    ├── libraries.md         # vue-query, axios, signalr, UI, PWA
    ├── architecture.md      # src/, anatomía de módulo, reglas estrictas
    ├── testing-and-tooling.md
    └── forms-and-validation.md
```

El SKILL.md es lo único que se carga siempre. Las references se leen on-demand desde la tabla de Decision Gates.

## Cómo integrarla en un CLAUDE.md de proyecto

Si querés que un proyecto Vue específico use esta arquitectura como contrato, agregá esto al `CLAUDE.md` del repo:

```markdown
## Arquitectura

Este proyecto sigue la arquitectura empresarial de referencia. Antes de tocar
código nuevo en `src/modules/`, `src/lib/`, `src/services/` o `src/composables/`,
cargá la skill `enterprise-frontend-architecture` y respetá sus Hard Rules:

- Imports desde `@/modules/<x>` (nunca subcarpetas internas)
- DTO `*Api` no escapa de la capa de adapters
- Componentes consumen composables, nunca axios/HttpClient directo
- Eventos WebSocket invalidan cachés de vue-query (no mutan estado local)

Ver `~/.claude/skills/enterprise-frontend-architecture/SKILL.md` para el contrato completo.
```

## Cómo actualizarla

Cuando la arquitectura de referencia evolucione en Obsidian:

1. Editá la `references/` correspondiente (no el SKILL.md, salvo que cambien las Hard Rules).
2. Versioná bumpando `metadata.version` en el frontmatter de SKILL.md.
3. Re-ejecutá `/skill-registry` si tenés ese skill instalado, para reindexar.

## Fuente

Basada en `C:\Users\hikig\Documents\Obsidian\hikig\Arquitectura\Referencia de Frontend Empresarial.md` (snapshot del 2026-05-26).
