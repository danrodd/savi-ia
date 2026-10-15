<script setup lang="ts">
import { useId } from 'vue'

defineProps<{
  label: string
  description?: string
  disabled?: boolean
}>()

const model = defineModel<boolean>({ default: false })
const id = `checkbox-${useId()}`
</script>

<template>
  <label class="ui-check" :class="{ 'ui-check--disabled': disabled }" :for="id">
    <input
      :id="id"
      v-model="model"
      class="ui-check__box"
      type="checkbox"
      :disabled="disabled"
      :aria-describedby="description ? `${id}-desc` : undefined"
    />
    <span class="ui-check__text">
      <span class="ui-check__label">{{ label }}</span>
      <span v-if="description" :id="`${id}-desc`" class="ui-check__description">{{ description }}</span>
    </span>
  </label>
</template>

<style scoped>
.ui-check {
  display: inline-flex;
  align-items: flex-start;
  gap: var(--space-3);
  min-height: 32px;
  padding: var(--space-1) 0;
  cursor: pointer;
}

.ui-check--disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.ui-check__box {
  flex-shrink: 0;
  width: 16px;
  height: 16px;
  margin: 2px 0 0;
  accent-color: var(--brand);
  cursor: inherit;
}

.ui-check__box:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 2px;
}

.ui-check__text {
  display: grid;
  gap: 2px;
}

.ui-check__label {
  font-size: 13px;
  color: var(--text);
}

.ui-check__description {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
}
</style>
