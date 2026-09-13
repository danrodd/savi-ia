<script setup lang="ts">
import type { AvailableErpDatabase } from '@/modules/admin'

defineProps<{ databases: AvailableErpDatabase[] }>()

const selected = defineModel<string | null>({ required: true })
</script>

<template>
  <div class="dbpicker">
    <label class="dbpicker__label" for="chat-database-picker">Cliente</label>
    <select id="chat-database-picker" v-model="selected" class="dbpicker__select">
      <option :value="null">Base con la que iniciaste sesión</option>
      <option v-for="db in databases" :key="db.id" :value="db.id">{{ db.name }}</option>
    </select>
    <span class="dbpicker__hint">Se fija al enviar el primer mensaje.</span>
  </div>
</template>

<style scoped>
.dbpicker {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: var(--space-2) var(--space-3);
  padding: 0 var(--space-5) var(--space-2);
  flex-shrink: 0;
}

.dbpicker__label {
  font-size: 11px;
  font-weight: var(--fw-medium);
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.dbpicker__select {
  height: 32px;
  max-width: 100%;
  padding: 0 var(--space-3);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
}

.dbpicker__select:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
}

.dbpicker__hint {
  font-size: 11px;
  color: var(--text-subtle);
}
</style>
