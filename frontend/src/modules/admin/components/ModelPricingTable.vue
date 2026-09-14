<script setup lang="ts">
import type { ModelPricing } from '../types'

const props = defineProps<{ models: string[]; pricing: Record<string, ModelPricing> }>()

function price(model: string): ModelPricing {
  return props.pricing[model] ?? { input: 0, output: 0, cache_read: 0, cache_write: 0 }
}

function update(model: string, key: keyof ModelPricing, value: string): void {
  const current = price(model)
  props.pricing[model] = { ...current, [key]: Number(value) || 0 }
}
</script>

<template>
  <div class="pricing">
    <p class="pricing__hint">USD por millón de tokens. Completa el precio del modelo de chat para registrar costos.</p>
    <div v-if="models.length === 0" class="pricing__empty">Elige al menos un modelo.</div>
    <div v-for="model in models" :key="model" class="pricing__row">
      <strong class="pricing__model">{{ model }}</strong>
      <label v-for="key in ['input', 'output', 'cache_read', 'cache_write'] as const" :key="key">
        <span>{{ key === 'cache_read' ? 'Lectura caché' : key === 'cache_write' ? 'Escritura caché' : key === 'input' ? 'Entrada' : 'Salida' }}</span>
        <input :value="price(model)[key]" type="number" min="0" step="0.0001" @input="update(model, key, ($event.target as HTMLInputElement).value)" />
      </label>
    </div>
  </div>
</template>

<style scoped>
.pricing__hint { margin: 0 0 var(--space-4); color: var(--text-muted); font-size: 12px; }
.pricing__empty { padding: var(--space-4); color: var(--text-subtle); background: var(--surface-subtle); border-radius: var(--r-sm); }
.pricing__row { display: grid; grid-template-columns: minmax(130px, 1.4fr) repeat(4, minmax(80px, 1fr)); gap: var(--space-3); align-items: end; padding: var(--space-3) 0; border-bottom: 1px solid var(--border); }
.pricing__model { overflow-wrap: anywhere; font-size: 12px; }
label { display: grid; gap: 3px; color: var(--text-muted); font-size: 10px; }
input { width: 100%; min-width: 0; padding: 6px; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-sm); font: inherit; }
@media (max-width: 700px) { .pricing__row { grid-template-columns: 1fr 1fr; } .pricing__model { grid-column: 1 / -1; } }
</style>
