<script setup lang="ts">
import { TriangleAlert } from 'lucide-vue-next'
import { computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'

import { useCloudLinkStore } from '../stores/cloudLinkStore'
import { globalAlertText } from '../utils/cloudLink'

const store = useCloudLinkStore()

const text = computed(() => (store.state ? globalAlertText(store.state) : ''))

// Si el estado no se puede consultar, no se molesta: el aviso es solo informativo.
onMounted(() => void store.load())
</script>

<template>
  <div v-if="store.showGlobalAlert" class="cab" role="alert" data-testid="cloud-alert">
    <TriangleAlert :size="16" aria-hidden="true" />
    <span>{{ text }}</span>
    <RouterLink :to="{ name: 'admin-cloud' }" class="cab__link">Ver SAVI Cloud</RouterLink>
  </div>
</template>

<style scoped>
.cab {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-5);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--r-sm);
  background: var(--surface-danger);
  color: var(--text-danger);
  font-size: 13px;
}
.cab__link { margin-left: auto; color: inherit; font-weight: var(--fw-semibold); text-decoration: underline; }
</style>
