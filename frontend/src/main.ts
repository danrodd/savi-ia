import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import './assets/styles/tokens.css'
import { installAuthBridge } from './lib/authBridge'
import { useAuthStore } from './modules/auth/stores/authStore'
import router from './router'

const app = createApp(App)

const pinia = createPinia()
app.use(pinia)
app.use(router)

// Bridge entre HttpClient y el store/router — debe quedar instalado
// ANTES de cualquier request. El store ya está disponible porque pinia
// se montó arriba; el router también.
const authStore = useAuthStore()
installAuthBridge({
  getAccessToken: () => authStore.accessToken,
  refreshAccessToken: () => authStore.ensureFreshAccessToken(),
  clearSession: () => {
    authStore.clearSession()
  },
  redirectToLogin: (nextPath) => {
    void router.push({
      name: 'login',
      query: nextPath && nextPath !== '/login' ? { next: nextPath } : undefined,
    })
  },
})

app.mount('#app')
