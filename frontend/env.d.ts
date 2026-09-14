/// <reference types="vite/client" />

/** Versión de SAVI (tag de git), incrustada por `vite.config.ts`. */
declare const __APP_VERSION__: string

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
