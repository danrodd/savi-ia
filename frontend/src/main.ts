import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import './assets/styles/tokens.css'
import { installAuthBridge } from './lib/authBridge'
import { useAuthStore } from './modules/auth/stores/authStore'
import { usePermisosStore, vModule } from './modules/permisos'
import router from './router'

const app = createApp(App)

const pinia = createPinia()
app.use(pinia)
app.use(router)

// Directiva global v-module — uso: <Button v-module="M.CONTABILIDAD">
app.directive('module', vModule)

// Bridge entre HttpClient y el store/router — debe quedar instalado
// ANTES de cualquier request. El store ya está disponible porque pinia
// se montó arriba; el router también.
const authStore = useAuthStore()
const permisosStore = usePermisosStore()
installAuthBridge({
  getAccessToken: () => authStore.accessToken,
  refreshAccessToken: () => authStore.ensureFreshAccessToken(),
  clearSession: () => {
    authStore.clearSession()
    permisosStore.clearPermisos()
  },
  redirectToLogin: (nextPath) => {
    void router.push({
      name: 'login',
      query: nextPath && nextPath !== '/login' ? { next: nextPath } : undefined,
    })
  },
  reloadPermisos: () => {
    void permisosStore.cargarBootstrap()
  },
})

// Si arrancamos con sesión persistida en localStorage, cargamos el
// bootstrap de permisos antes del primer render para que los guards
// y la UI tengan el set fresco.
if (authStore.isAuthenticated) {
  void permisosStore.cargarBootstrap()
}

app.mount('#app')
