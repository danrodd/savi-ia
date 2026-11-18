<script setup lang="ts">
import { nextTick, onMounted, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import AccessPolicyCard from '@/components/AccessPolicyCard.vue'
import AiPolicyCard from '@/components/AiPolicyCard.vue'
import ClientPolicyCard from '@/components/ClientPolicyCard.vue'
import GroupCapsSummary from '@/components/GroupCapsSummary.vue'
import { useClientContext } from '@/lib/clientContext'
import { CONFIG_SECTIONS, type ConfigSection } from '@/lib/clientRoutes'

/**
 * Configuración del cliente: Instalaciones, IA y Acceso, una sección a la vez (antes eran
 * nueve tarjetas en una sola página). La sección va en el ancla (`#ia`), que es lo que usan
 * los enlaces de la puesta en marcha. Las otras secciones se ocultan pero no se desmontan:
 * cada tarjeta guarda por su cuenta y sus cambios sin guardar sobreviven al cambio de sección.
 */
const { id, client, reload } = useClientContext()
const route = useRoute()

const LABELS: Record<ConfigSection, string> = {
  instalaciones: 'Instalaciones',
  ia: 'IA',
  acceso: 'Acceso',
}

function current(): ConfigSection {
  const hash = route.hash.slice(1)
  return CONFIG_SECTIONS.find((s) => s === hash) ?? 'instalaciones'
}

/** El router no desplaza por sí solo hasta el ancla: lo hace esta página. */
function reveal(): void {
  const hash = route.hash.slice(1)
  if (!CONFIG_SECTIONS.some((s) => s === hash)) return
  void nextTick(() => {
    document.getElementById(`config-${hash}`)?.scrollIntoView?.({ block: 'start' })
  })
}

onMounted(reveal)
watch(() => route.hash, reveal)
</script>

<template>
  <div v-if="client" class="config" data-test="config">
    <nav class="config__nav" aria-label="Secciones de configuración">
      <RouterLink
        v-for="section in CONFIG_SECTIONS"
        :key="section"
        :to="{ hash: `#${section}` }"
        replace
        class="config__link"
        :class="{ 'config__link--active': current() === section }"
        :aria-current="current() === section ? 'true' : undefined"
        :data-test="`config-nav-${section}`"
      >
        {{ LABELS[section] }}
      </RouterLink>
    </nav>

    <section
      v-show="current() === 'instalaciones'"
      id="config-instalaciones"
      class="config__section"
      aria-labelledby="config-h-instalaciones"
    >
      <h2 id="config-h-instalaciones" class="config__title">Instalaciones</h2>
      <ClientPolicyCard :client-id="id" :client="client" @saved="reload()" />
    </section>

    <section v-show="current() === 'ia'" id="config-ia" class="config__section" aria-labelledby="config-h-ia">
      <h2 id="config-h-ia" class="config__title">IA</h2>
      <AiPolicyCard :client-id="id" :policy="client.ai_policy" @saved="reload()" />
      <GroupCapsSummary :groups="client.access_policy.groups" />
    </section>

    <section
      v-show="current() === 'acceso'"
      id="config-acceso"
      class="config__section"
      aria-labelledby="config-h-acceso"
    >
      <h2 id="config-h-acceso" class="config__title">Acceso</h2>
      <AccessPolicyCard :client-id="id" :policy="client.access_policy" @saved="reload()" />
    </section>
  </div>
</template>

<style scoped>
.config {
  display: grid;
  gap: var(--space-6);
}

.config__nav {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.config__link {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-pill);
  background: var(--surface-elev);
  color: var(--text-muted);
  font-size: 12.5px;
  font-weight: var(--fw-medium);
  text-decoration: none;
}

.config__link:hover {
  color: var(--text);
}

.config__link--active {
  border-color: var(--brand);
  color: var(--text);
}

.config__section {
  display: grid;
  gap: var(--space-6);
  align-content: start;
  scroll-margin-top: var(--space-4);
}

.config__title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: var(--fw-semibold);
  color: var(--text);
}
</style>
