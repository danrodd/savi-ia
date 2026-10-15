<script setup lang="ts">
import { Badge, Card } from '@savi/ui'
import { RouterLink } from 'vue-router'
import { formatUsd } from '@/lib/format'
import type { AccessGroup } from '@/lib/types'

/**
 * Los topes de IA por grupo se editan en Acceso (junto a las bases del grupo). Aquí solo se
 * resumen, para que quien configura la IA vea el cuadro completo y sepa dónde cambiarlos.
 */
defineProps<{ groups: AccessGroup[] }>()
</script>

<template>
  <Card
    title="Topes por grupo"
    description="Cada grupo puede tener un tope mensual por persona. Reemplaza el tope general para sus miembros."
    data-test="group-caps"
  >
    <ul v-if="groups.length" class="caps">
      <li v-for="g in groups" :key="g.id ?? g.name" class="caps__item" data-test="group-cap">
        <strong>{{ g.name }}</strong>
        <Badge>{{ g.members.length }} {{ g.members.length === 1 ? 'persona' : 'personas' }}</Badge>
        <span class="caps__value num">
          {{ g.user_monthly_usd ? `${formatUsd(g.user_monthly_usd)} / mes` : 'Sin tope' }}
        </span>
      </li>
    </ul>
    <p v-else class="muted caps__empty" data-test="group-caps-empty">
      Todavía no hay grupos. Se crean en Acceso.
    </p>
    <RouterLink :to="{ hash: '#acceso' }" replace class="caps__link" data-test="group-caps-link">
      Editar los topes en Acceso
    </RouterLink>
  </Card>
</template>

<style scoped>
.caps {
  display: grid;
  gap: var(--space-2);
  margin: 0 0 var(--space-4);
  padding: 0;
  list-style: none;
}

.caps__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface);
  font-size: 13px;
}

.caps__value {
  margin-left: auto;
  color: var(--text-muted);
}

.caps__empty {
  margin: 0 0 var(--space-4);
  font-size: 13px;
}

.caps__link {
  font-size: 12.5px;
  font-weight: var(--fw-medium);
}
</style>
