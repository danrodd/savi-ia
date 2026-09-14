import { execFileSync } from 'node:child_process'
import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import vueDevTools from 'vite-plugin-vue-devtools'

/**
 * Versión incrustada en el bundle. No se escribe a mano: es el tag de git.
 *
 * - `VITE_APP_VERSION` la fija `installer/build.ps1`, que la calcula UNA
 *   vez con `scripts/version.py` para backend, frontend e instalador.
 * - Sin esa variable (desarrollo, Vitest) se calcula acá con los mismos
 *   argumentos de `git describe` que usa el script.
 * - Sin git, `0.0.0-dev`: nunca un número que parezca real.
 */
function resolveAppVersion(): string {
  if (process.env.VITE_APP_VERSION) return process.env.VITE_APP_VERSION
  try {
    return execFileSync(
      'git',
      ['describe', '--tags', '--always', '--dirty=-sucio', '--match', 'v*'],
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] },
    ).trim()
  } catch {
    return '0.0.0-dev'
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue(), vueDevTools()],
  define: {
    __APP_VERSION__: JSON.stringify(resolveAppVersion()),
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})
