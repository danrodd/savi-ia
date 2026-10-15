// Aplica el tema guardado antes del primer pintado: sin esto, quien usa el modo oscuro ve un
// destello claro al cargar. La misma clave usa `useTheme` (src/lib/theme.ts).
;(() => {
  try {
    // `useTheme` (VueUse) guarda el modo como texto plano: `dark`, no `"dark"`. Se toleran
    // las comillas por si quedó un valor viejo serializado como JSON.
    const stored = localStorage.getItem('savi-cloud-theme-mode')
    const mode = stored ? stored.replace(/^"|"$/g, '') : 'system'
    const dark =
      mode === 'dark' ||
      (mode === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
    if (dark) document.documentElement.classList.add('dark')
  } catch {
    // Sin acceso a localStorage (modo privado estricto): queda el tema claro.
  }
})()
