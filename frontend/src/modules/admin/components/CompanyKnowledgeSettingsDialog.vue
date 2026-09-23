<script setup lang="ts">
/**
 * Configuración de Conocimiento: el interruptor de la lectura de PDF con IA.
 *
 * Es la única decisión que toma el administrador. No hay una casilla por
 * archivo: con la lectura activa, cada PDF que se suba se lee con IA y el
 * diálogo de subida muestra antes cuánto costaría.
 */
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import Button from '@/components/ui/Button.vue'
import Dialog from '@/components/ui/Dialog.vue'
import { toast } from '@/lib/toast'
import { useCompanyDocumentStore } from '../stores/companyDocumentStore'
import { approxUsd } from '../utils/aiReading'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const store = useCompanyDocumentStore()
const saving = ref(false)

const settings = computed(() => store.aiReading)
const pricePer100 = computed(() => {
  const perPage = settings.value?.estimated_usd_per_page
  return perPage === null || perPage === undefined ? null : approxUsd(perPage * 100)
})

watch(
  () => props.open,
  (open) => {
    if (open) void store.loadAiReading()
  },
  { immediate: true },
)

async function onToggle(event: Event): Promise<void> {
  const enabled = (event.target as HTMLInputElement).checked
  saving.value = true
  try {
    await store.setAiReading(enabled)
    toast.success(enabled ? 'Lectura con IA activada' : 'Lectura con IA desactivada')
  } catch (e) {
    toast.error((e as Error).message || 'No se pudo guardar la configuración.')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog
    :open="open"
    title="Configuración de Conocimiento"
    :max-width="520"
    @update:open="(value) => emit('update:open', value)"
  >
    <p v-if="!settings" class="kset__hint">Cargando…</p>
    <div v-else class="kset">
      <label class="kset__switch">
        <input
          type="checkbox"
          role="switch"
          class="kset__input"
          :checked="settings.ai_reading_enabled"
          :disabled="saving || !settings.available"
          @change="onToggle"
        />
        <span class="kset__track" aria-hidden="true"><span class="kset__thumb" /></span>
        <span class="kset__label">
          <strong>Leer PDF con IA</strong>
          <span class="kset__sub">Tablas, imágenes, planos y documentos escaneados.</span>
        </span>
      </label>

      <p v-if="!settings.available" class="kset__warn" role="status">
        {{ settings.unavailable_reason ?? 'No hay un proveedor de IA disponible.' }}
        Sin proveedor, los PDF se leen solo por su texto digital.
      </p>

      <dl v-else class="kset__facts">
        <div>
          <dt>Proveedor</dt>
          <dd>{{ settings.provider_name }}</dd>
        </div>
        <div>
          <dt>Modelo de lectura</dt>
          <dd><code>{{ settings.model }}</code></dd>
        </div>
        <div>
          <dt>Costo estimado</dt>
          <dd>
            <template v-if="pricePer100">{{ pricePer100 }} cada 100 páginas</template>
            <template v-else>No disponible: el modelo no tiene precios configurados.</template>
          </dd>
        </div>
      </dl>

      <p class="kset__hint">
        El proveedor y el modelo se cambian en
        <RouterLink :to="{ name: 'admin-llm-providers' }" @click="emit('update:open', false)">
          Proveedores de IA</RouterLink
        >.
      </p>

      <p v-if="settings.uses_subscription" class="kset__warn">
        La lectura consume el límite de tu suscripción de Claude. Una carga grande puede dejar el
        chat sin servicio hasta que el límite se renueve. El costo se muestra como referencia de
        precio de lista.
      </p>

      <p class="kset__notice">{{ settings.privacy_notice }}</p>
      <p class="kset__hint">
        Aplica a lo que se suba desde ahora. Los documentos que ya están cargados se pueden leer con
        IA desde la tabla, con "Leer con IA".
      </p>
    </div>

    <template #footer>
      <Button variant="ghost" @click="emit('update:open', false)">Cerrar</Button>
    </template>
  </Dialog>
</template>

<style scoped>
.kset {
  display: grid;
  gap: var(--space-3);
}

.kset__switch {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  cursor: pointer;
}

.kset__input {
  position: absolute;
  opacity: 0;
  width: 1px;
  height: 1px;
}

.kset__track {
  flex-shrink: 0;
  position: relative;
  width: 36px;
  height: 20px;
  margin-top: 2px;
  border-radius: 999px;
  background: var(--border);
  transition: background var(--duration-fast, 120ms) ease;
}

.kset__thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--surface-elev, #fff);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
  transition: transform var(--duration-fast, 120ms) ease;
}

.kset__input:checked + .kset__track {
  background: var(--brand);
}

.kset__input:checked + .kset__track .kset__thumb {
  transform: translateX(16px);
}

.kset__input:focus-visible + .kset__track {
  outline: 2px solid var(--brand-ring);
  outline-offset: 2px;
}

.kset__input:disabled + .kset__track {
  opacity: 0.5;
}

.kset__label {
  display: grid;
  gap: 2px;
  font-size: 14px;
  color: var(--text);
}

.kset__sub,
.kset__hint {
  font-size: 12px;
  color: var(--text-subtle);
}

.kset__hint {
  margin: 0;
}

.kset__facts {
  display: grid;
  gap: var(--space-2);
  margin: 0;
  font-size: 13px;
}

.kset__facts div {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--space-2);
}

.kset__facts dt {
  color: var(--text-muted);
}

.kset__facts dd {
  margin: 0;
  color: var(--text);
  text-align: right;
}

.kset__warn,
.kset__notice {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-sm);
  font-size: 12px;
}

.kset__warn {
  background: var(--surface-warn, rgba(234, 179, 8, 0.12));
  color: var(--text);
}

.kset__notice {
  background: var(--surface-subtle);
  color: var(--text-muted);
}
</style>
