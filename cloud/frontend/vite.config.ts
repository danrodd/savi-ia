import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// En desarrollo el API de Cloud corre en :8001 (el :8000 es el backend de SAVI). En producción
// la consola se sirve desde el mismo origen que el API, así que no hay CORS ni URL configurable.
const API_TARGET = process.env.CLOUD_API_TARGET ?? 'http://localhost:8001'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5174,
    proxy: {
      '/console/auth': API_TARGET,
      '/console/api': API_TARGET,
    },
  },
})
