<script setup lang="ts">
import { Button, EmptyState } from '@savi/ui'
import type { Component } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

/**
 * Vacío de una lista que se llena sola cuando hay una instalación reportando: explica por qué
 * está vacía y lleva al paso que falta. Sin instalaciones, a Vinculación (si el rol puede
 * generar tokens; si no, avisa a quién pedirlo). Con instalaciones, a verlas.
 */
const props = defineProps<{
  clientId: string
  icon: Component
  title: string
  /** Por qué está vacío. */
  description: string
  /** El cliente ya tiene instalaciones vinculadas (aún no reportaron). */
  hasInstances?: boolean
}>()

const router = useRouter()
const auth = useAuthStore()

function go(tab: string): void {
  void router.push(`/clientes/${props.clientId}/${tab}`)
}
</script>

<template>
  <EmptyState :icon="icon" :title="title" :description="description">
    <Button v-if="hasInstances" variant="secondary" data-test="empty-cta" @click="go('instancias')">
      Ver instalaciones
    </Button>
    <Button
      v-else-if="auth.can('tokens.manage')"
      variant="secondary"
      data-test="empty-cta"
      @click="go('vinculacion')"
    >
      Vincular una instalación
    </Button>
    <p v-else class="empty-hint" data-test="empty-role-hint">
      Pide a Soporte que vincule una instalación.
    </p>
  </EmptyState>
</template>

<style scoped>
.empty-hint {
  margin: 0;
  font-size: 12.5px;
  color: var(--text-muted);
}
</style>
