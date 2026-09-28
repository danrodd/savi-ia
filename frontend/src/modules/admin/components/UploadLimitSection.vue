<script setup lang="ts">
/**
 * Cupo de cargas por usuario y por hora, dentro de la Configuración.
 *
 * Subir, reemplazar, agregar un sitio y "Leer ahora" comparten el cupo:
 * todas encolan procesamiento. El servidor fija el valor por defecto y un
 * techo; acá el administrador elige dentro de ese techo sin tocar el
 * servidor.
 */
import { computed, onMounted, ref, watch } from 'vue'

import Button from '@/components/ui/Button.vue'
import { toast } from '@/lib/toast'
import { useCompanyDocumentStore } from '../stores/companyDocumentStore'

const store = useCompanyDocumentStore()
const value = ref<number | null>(null)
const saving = ref(false)
const error = ref<string | null>(null)

const limit = computed(() => store.uploadLimit)
const isCustom = computed(() => limit.value?.upload_limit_per_hour != null)
const changed = computed(() => value.value !== limit.value?.effective)

watch(
  limit,
  (current) => {
    value.value = current?.effective ?? null
  },
  { immediate: true },
)

onMounted(() => void store.loadUploadLimit())

async function save(perHour: number | null): Promise<void> {
  const current = limit.value
  if (!current) return
  if (
    perHour !== null &&
    (!Number.isInteger(perHour) || perHour < 1 || perHour > current.maximum)
  ) {
    error.value = `Elige un número entre 1 y ${current.maximum}.`
    return
  }
  error.value = null
  saving.value = true
  try {
    const saved = await store.setUploadLimit(perHour)
    toast.success(`Cupo de cargas: ${saved.effective} por hora`)
  } catch (e) {
    error.value = (e as Error).message || 'No se pudo guardar el cupo.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="ulimit" aria-labelledby="ulimit-title">
    <p id="ulimit-title" class="ulimit__title">Cupo de cargas</p>
    <p v-if="!limit" class="ulimit__hint">Cargando…</p>
    <template v-else>
      <p class="ulimit__hint">
        Cuántas veces por hora puede cada usuario subir o reemplazar un documento, agregar un sitio
        o pedir que se lea de nuevo. Frena cargas masivas por error o por un script.
      </p>
      <form class="ulimit__row" novalidate @submit.prevent="save(value)">
        <input
          v-model.number="value"
          class="ulimit__input"
          type="number"
          min="1"
          :max="limit.maximum"
          aria-label="Cargas por hora por usuario"
          :disabled="saving"
        />
        <span class="ulimit__unit">por hora</span>
        <Button type="submit" size="sm" :loading="saving" :disabled="!changed">Guardar</Button>
        <Button
          v-if="isCustom"
          type="button"
          variant="ghost"
          size="sm"
          :disabled="saving"
          @click="save(null)"
        >
          Volver a {{ limit.default }}
        </Button>
      </form>
      <p class="ulimit__hint">
        {{ isCustom ? `Por defecto del servidor: ${limit.default}.` : 'Valor por defecto del servidor.' }}
        Máximo permitido: {{ limit.maximum }}.
      </p>
      <p v-if="error" class="ulimit__error" role="alert">{{ error }}</p>
    </template>
  </section>
</template>

<style scoped>
.ulimit {
  display: grid;
  gap: var(--space-2);
  padding-top: var(--space-4);
  border-top: 1px solid var(--border);
}

.ulimit__title {
  margin: 0;
  font-size: 14px;
  font-weight: var(--fw-semibold);
  color: var(--text);
}

.ulimit__hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-subtle);
}

.ulimit__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.ulimit__input {
  width: 96px;
  height: 34px;
  padding: 0 var(--space-3);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text);
  font: inherit;
  font-size: 13px;
}

.ulimit__input:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
}

.ulimit__unit {
  font-size: 13px;
  color: var(--text-muted);
}

.ulimit__error {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  background: var(--surface-danger, rgba(220, 38, 38, 0.08));
  color: var(--text-danger, #b91c1c);
  font-size: 12px;
}
</style>
