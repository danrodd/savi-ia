import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import { configureHttp } from './lib/http'
import router from './router'
import { useAuthStore } from './stores/authStore'
import './styles/tokens.css'
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
