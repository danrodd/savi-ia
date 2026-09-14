/**
 * Setup global de Vitest.
 *
 * Vitest 4 + jsdom 29 no exponen `window.localStorage` (queda
 * `undefined`, no lanza) sin importar la URL del entorno. `authStore` y
 * `permisosStore` lo usan para persistir sesión: cualquier componente
 * que dispare su inicialización (por ejemplo `App.vue`, vía
 * `usePermisosPolling`) revienta al montarse en un test si no hay un
 * polyfill.
 */
class MemoryStorage implements Storage {
  private store = new Map<string, string>()

  get length(): number {
    return this.store.size
  }

  clear(): void {
    this.store.clear()
  }

  getItem(key: string): string | null {
    return this.store.has(key) ? (this.store.get(key) as string) : null
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null
  }

  removeItem(key: string): void {
    this.store.delete(key)
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value))
  }
}

if (typeof window !== 'undefined' && !window.localStorage) {
  Object.defineProperty(window, 'localStorage', { value: new MemoryStorage() })
}
if (typeof window !== 'undefined' && !window.sessionStorage) {
  Object.defineProperty(window, 'sessionStorage', { value: new MemoryStorage() })
}
