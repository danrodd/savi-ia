<script setup lang="ts">
/**
 * Quién puede consultar un documento y en qué bases aplica.
 * Lo comparten la subida y la edición.
 */
import { useId } from 'vue'

import { MODULE_LABELS, type ModuleCode } from '@/modules/permisos'
import type { DocumentPermissions, DocumentVisibility } from '../types'

defineProps<{
  databases: { id: string; name: string }[]
}>()

const permissions = defineModel<DocumentPermissions>({ required: true })
const uid = useId()

const VISIBILITY_OPTIONS: { value: DocumentVisibility; label: string; hint: string }[] = [
  { value: 'all', label: 'Toda la empresa', hint: 'Cualquier usuario con acceso a la base.' },
  {
    value: 'modules',
    label: 'Usuarios con ciertos módulos',
    hint: 'Quien tenga al menos uno de los módulos elegidos en el ERP.',
  },
  { value: 'admins', label: 'Solo administradores', hint: 'Administradores del ERP en esa base.' },
]

const MODULE_OPTIONS = Object.entries(MODULE_LABELS) as [ModuleCode, string][]

function setVisibility(value: DocumentVisibility): void {
  permissions.value = { ...permissions.value, visibility: value }
}

function toggle(list: 'modules' | 'database_ids', value: string): void {
  const current = permissions.value[list]
  const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value]
  permissions.value = { ...permissions.value, [list]: next }
}

function setAllDatabases(value: boolean): void {
  permissions.value = { ...permissions.value, all_databases: value }
}
</script>

<template>
  <div class="docperm">
    <fieldset class="docperm__group">
      <legend class="docperm__legend">¿Quién puede consultar este documento?</legend>
      <label v-for="option in VISIBILITY_OPTIONS" :key="option.value" class="docperm__radio">
        <input
          type="radio"
          :name="`${uid}-visibility`"
          :value="option.value"
          :checked="permissions.visibility === option.value"
          @change="setVisibility(option.value)"
        />
        <span>
          <span class="docperm__option">{{ option.label }}</span>
          <span class="docperm__hint">{{ option.hint }}</span>
        </span>
      </label>

      <div v-if="permissions.visibility === 'modules'" class="docperm__chips" role="group" aria-label="Módulos">
        <label
          v-for="[code, label] in MODULE_OPTIONS"
          :key="code"
          class="docperm__chip"
          :class="{ 'docperm__chip--on': permissions.modules.includes(code) }"
        >
          <input
            type="checkbox"
            class="docperm__sr"
            :checked="permissions.modules.includes(code)"
            @change="toggle('modules', code)"
          />
          {{ label }}
        </label>
        <p class="docperm__note">
          Los módulos salen de los permisos de cada usuario en el ERP. Si a alguien le quitan el
          módulo, deja de ver el documento en su próxima pregunta.
        </p>
      </div>
    </fieldset>

    <fieldset class="docperm__group">
      <legend class="docperm__legend">¿En qué bases aplica?</legend>
      <label class="docperm__radio">
        <input
          type="radio"
          :name="`${uid}-scope`"
          :checked="permissions.all_databases"
          @change="setAllDatabases(true)"
        />
        <span class="docperm__option">Todas las bases, incluidas las que se agreguen después</span>
      </label>
      <label class="docperm__radio">
        <input
          type="radio"
          :name="`${uid}-scope`"
          :checked="!permissions.all_databases"
          @change="setAllDatabases(false)"
        />
        <span class="docperm__option">Solo en algunas bases</span>
      </label>
      <div v-if="!permissions.all_databases" class="docperm__chips" role="group" aria-label="Bases">
        <label
          v-for="db in databases"
          :key="db.id"
          class="docperm__chip"
          :class="{ 'docperm__chip--on': permissions.database_ids.includes(db.id) }"
        >
          <input
            type="checkbox"
            class="docperm__sr"
            :checked="permissions.database_ids.includes(db.id)"
            @change="toggle('database_ids', db.id)"
          />
          {{ db.name }}
        </label>
      </div>
    </fieldset>
  </div>
</template>

<style scoped>
.docperm {
  display: grid;
  gap: var(--space-4);
}

.docperm__group {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  padding: 0;
  border: none;
  min-width: 0;
}

.docperm__legend {
  margin-bottom: var(--space-2);
  padding: 0;
  font-size: 11px;
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: var(--fw-medium);
}

.docperm__radio {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
}

.docperm__radio input {
  margin-top: 3px;
  accent-color: var(--brand);
}

.docperm__option {
  display: block;
  font-weight: var(--fw-medium);
}

.docperm__hint {
  display: block;
  font-size: 12px;
  color: var(--text-muted);
}

.docperm__chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding-left: var(--space-5);
}

.docperm__chip {
  padding: 4px var(--space-3);
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 12px;
  color: var(--text-muted);
  background: var(--surface-elev);
  cursor: pointer;
  user-select: none;
}

.docperm__chip:focus-within {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
}

.docperm__chip--on {
  border-color: var(--brand);
  background: var(--brand-soft);
  color: var(--brand-strong);
}

.docperm__note {
  flex-basis: 100%;
  margin: var(--space-1) 0 0;
  font-size: 11px;
  color: var(--text-subtle);
  line-height: 1.4;
}

.docperm__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
</style>
