import { fileURLToPath } from 'node:url'
import { configDefaults, defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      // La primera prueba de cada archivo que monta el router importa todas las vistas en frío;
      // con la suite en paralelo eso supera los 5 s por defecto sin que nada esté colgado.
      testTimeout: 15000,
      exclude: [...configDefaults.exclude, 'e2e/**'],
      setupFiles: [fileURLToPath(new URL('./src/__tests__/setup.ts', import.meta.url))],
    },
  }),
)
