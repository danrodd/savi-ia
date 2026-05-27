#!/usr/bin/env bash
# Starter kit para arrancar un proyecto Vue 3 empresarial con la arquitectura de referencia.
# Ejecutá los pasos en orden. Cada bloque es independiente.

set -e

# 1. Crear proyecto base (seleccioná: TS, Router, Pinia, Vitest, Playwright, ESLint)
pnpm create vue@latest

# 2. Instalar dependencias core funcionales
pnpm add @tanstack/vue-query axios pinia vue-router \
         vee-validate @vee-validate/zod zod \
         @vueuse/core lucide-vue-next vue-sonner \
         reka-ui class-variance-authority clsx tailwind-merge

# 3. Instalar herramientas de desarrollo, UI y linters
pnpm add -D tailwindcss @tailwindcss/vite tw-animate-css \
            shadcn-vue oxlint eslint-plugin-oxlint \
            vite-plugin-pwa @vite-pwa/assets-generator workbox-window \
            @playwright/test

# 4. Inicializar motor de UI
pnpm dlx shadcn-vue@latest init

# 5. Verificar Node engine
node -v  # Debe ser >=20.x
