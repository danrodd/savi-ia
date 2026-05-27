# Testing, Linting y Tooling

## Testing

| Capa | Herramienta | Notas |
|------|-------------|-------|
| Unitario / Componente | Vitest + jsdom + `@vue/test-utils` | Tests (`*.spec.ts`) co-localizados con el código que evalúan (ej. `HttpClient.spec.ts` junto a `HttpClient.ts`) |
| E2E | Playwright | Levanta el dev server automáticamente. Genera trazas y capturas SOLO en fallos |

## Linting y Formato — Cadena multi-capa

Combinación optimizada para velocidad + profundidad:

1. **oxlint (Rust)**: primera pasada ultra rápida — errores comunes en milisegundos.
2. **ESLint (flat config)**: pasada profunda con reglas basadas en tipos (`@vue/eslint-config-typescript`).
3. **eslint-plugin-oxlint**: desactiva en ESLint las reglas que oxlint ya evaluó (evita duplicidad).
4. **Prettier + eslint-config-prettier**: formateo sin conflictos con linter.

Script combinado: `pnpm lint` ejecuta la cadena en secuencia. Overrides explícitos para componentes UI autogenerados (shadcn) que relajan ciertas reglas estructurales.

## Code-Splitting

- **Vite `manualChunks`**: separar vendor (`vue`, `vue-router`, `pinia`, `vue-query`) del código de aplicación.
- **Lazy loading obligatorio** en todas las rutas:

```ts
{
  path: '/facturacion',
  component: () => import('@/modules/facturacion/views/FacturacionView.vue'),
}
```

## Co-localización de tests

```
src/lib/
├── HttpClient.ts
├── HttpClient.spec.ts     ← junto al archivo bajo prueba
├── errorMapper.ts
└── errorMapper.spec.ts
```

No agrupar tests en `__tests__/` separados — perjudica la navegación y la cohesión.
