<script setup lang="ts">
/**
 * 404 — cualquier URL que no matchee ninguna ruta.
 *
 * Sin esto el router no renderizaba nada y el usuario veía una pantalla en
 * blanco: indistinguible de una app rota. Un typo en el enlace compartido de
 * una conversación bastaba para llegar acá.
 *
 * No redirige sola al inicio: una redirección automática esconde el error y
 * deja al usuario preguntándose por qué terminó en otro lado.
 */
import { computed } from 'vue'

import { useRoute, useRouter } from 'vue-router'

import Button from '@/components/ui/Button.vue'
import { useAuthStore } from '@/modules/auth/stores/authStore'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const attemptedPath = computed(() => route.fullPath)

function goHome(): void {
  void router.push(auth.isAuthenticated ? { name: 'home' } : { name: 'login' })
}

function goBack(): void {
  // `back()` solo si hay historial propio: si se entró directo por URL,
  // volvería fuera de la app.
  if (window.history.length > 1) router.back()
  else goHome()
}
</script>

<template>
  <div class="not-found">
    <div class="not-found__card">
      <p class="not-found__code" aria-hidden="true">404</p>
      <h1 class="not-found__title">Esta página no existe</h1>
      <p class="not-found__msg">
        No encontramos nada en esta dirección. Puede que el enlace esté mal
        escrito o que la página ya no esté.
      </p>
      <!-- En su propia línea y no dentro de la frase: una ruta larga se parte
           en cualquier lado y deja la puntuación colgando. -->
      <p class="not-found__path">{{ attemptedPath }}</p>
      <div class="not-found__actions">
        <Button variant="ghost" @click="goBack">Volver</Button>
        <Button @click="goHome">Ir al inicio</Button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.not-found {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: var(--bg);
  padding: var(--space-6);
}

.not-found__card {
  width: min(480px, 100%);
  padding: var(--space-7);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-md);
  text-align: center;
}

.not-found__code {
  margin: 0 0 var(--space-2);
  font-size: 56px;
  line-height: 1;
  font-weight: var(--fw-semibold);
  color: var(--text-muted);
  opacity: 0.4;
  letter-spacing: -0.03em;
}

.not-found__title {
  margin: 0 0 var(--space-3);
  font-size: 22px;
  font-weight: var(--fw-semibold);
  color: var(--text);
}

.not-found__msg {
  margin: 0 0 var(--space-4);
  color: var(--text-muted);
  font-size: 14px;
  line-height: 1.5;
}

.not-found__path {
  margin: 0 0 var(--space-6);
  font-family: var(--font-mono, ui-monospace, monospace);
  font-size: 12px;
  color: var(--text);
  background: var(--surface-subtle);
  border-radius: var(--r-sm);
  padding: var(--space-2) var(--space-3);
  /* Una ruta larga no puede empujar el ancho de la tarjeta en un teléfono. */
  overflow-wrap: anywhere;
}

.not-found__actions {
  display: flex;
  justify-content: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}
</style>
