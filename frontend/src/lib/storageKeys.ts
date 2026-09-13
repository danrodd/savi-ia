export const STORAGE_PREFIX = 'savi-agent' as const

export const STORAGE_KEYS = {
  THEME_MODE: `${STORAGE_PREFIX}-theme-mode`,
  SIDEBAR_OPEN: `${STORAGE_PREFIX}-sidebar-open`,
  ACCESS_TOKEN: `${STORAGE_PREFIX}-access-token`,
  REFRESH_TOKEN: `${STORAGE_PREFIX}-refresh-token`,
  AUTH_USER: `${STORAGE_PREFIX}-auth-user`,
  PERMISOS_MODULES: `${STORAGE_PREFIX}-permisos-modules`,
  PERMISOS_VERSION: `${STORAGE_PREFIX}-permisos-version`,
  LOGIN_DATABASE_CODES: `${STORAGE_PREFIX}-login-database-codes`,
} as const

export type StorageKey = (typeof STORAGE_KEYS)[keyof typeof STORAGE_KEYS]
