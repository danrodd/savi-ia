/**
 * Aplica el tema guardado ANTES del primer pintado, para que quien usa el
 * modo oscuro no vea un destello claro al cargar.
 *
 * Vive en un archivo y no embebido en `index.html` a propósito: la CSP del
 * backend usa `script-src 'self'`, y permitir `'unsafe-inline'` para este
 * script chico desarmaría la defensa contra XSS de toda la aplicación.
 */
;(() => {
  try {
    const stored = localStorage.getItem('savi-agent-theme-mode')
    const mode = stored ? JSON.parse(stored) : 'system'
    const isDark =
      mode === 'dark' ||
      (mode === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
    if (isDark) document.documentElement.classList.add('dark')
  } catch (_) {}
})()
