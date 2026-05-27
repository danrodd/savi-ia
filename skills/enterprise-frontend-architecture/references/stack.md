# Stack Base

| Capa | Tecnología | Versión Referencial | Función |
|------|------------|---------------------|---------|
| Framework UI | Vue 3 (Composition API + `<script setup>`) | ^3.5.0 | Framework reactivo principal |
| Lenguaje | TypeScript | ~5.x / 6.x | Tipado estático en todo el proyecto, incluido `.vue` |
| Bundler / Dev server | Vite | ^5.x | Build, HMR, proxy hacia el backend, code-splitting |
| Gestor de paquetes | pnpm (workspace) | — | Lockfile `pnpm-lock.yaml`, configuración multi-paquete |
| Type-checker | vue-tsc | ^2.x / 3.x | Reemplaza a `tsc` para entender `.vue` |
| Runtime | Node | >=20.x | Definido estrictamente en `engines` del `package.json` |

## Reglas no negociables

- `engines.node` >=20 en `package.json` (la app debe negarse a instalar en runtimes viejos).
- `pnpm` es el único gestor de paquetes soportado — no mezclar con npm/yarn.
- Type-checking con `vue-tsc`, no con `tsc` directo.
- `strict: true` en `tsconfig.json`. Sin `any` implícito.
