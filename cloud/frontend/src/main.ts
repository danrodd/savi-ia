import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import { configureHttp } from './lib/http'
import router from './router'
import { useAuthStore } from './stores/authStore'
// Fuentes servidas desde el propio build: la CSP de la consola no permite orígenes externos.
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import '@fontsource/poppins/500.css'
import '@fontsource/poppins/600.css'
import '@fontsource/poppins/700.css'
import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import '@savi/ui/tokens.css'
import './styles/base.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
app.use(router)

// El cliente HTTP necesita el token y la renovación de sesión sin importar el store (evita
// una dependencia circular): se conectan acá, antes de la primera petición.
const auth = useAuthStore()
configureHttp({
  getAccessToken: () => auth.accessToken,
  refresh: () => auth.refresh(),
  onSessionLost: () => {
    auth.clearSession()
    const current = router.currentRoute.value
    if (!current.meta.public) {
      void router.push({
        name: 'login',
        query: current.fullPath !== '/' ? { next: current.fullPath } : undefined,
      })
    }
  },
})

app.mount('#app')
