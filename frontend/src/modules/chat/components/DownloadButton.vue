<script setup lang="ts">
withDefaults(defineProps<{ label?: string }>(), { label: 'Descargar' })
defineEmits<{ click: [] }>()
</script>

<template>
  <button type="button" class="dl-btn" :aria-label="label" @click="$emit('click')">
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <path d="M12 3v12" />
      <path d="m7 11 5 5 5-5" />
      <path d="M5 21h14" />
    </svg>
  </button>
</template>

<style scoped>
.dl-btn {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text-muted);
  box-shadow: var(--shadow-xs);
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out);
}

.dl-btn:hover {
  background: var(--surface-hover);
  color: var(--text);
}
</style>
