<script setup lang="ts">
withDefaults(defineProps<{ size?: number; label?: string }>(), { size: 28, label: 'S' })
</script>

<template>
  <span class="brand-mark" :style="{ width: `${size}px`, height: `${size}px` }">
    <span class="brand-mark__glyph">{{ label }}</span>
    <span class="brand-mark__dot" aria-hidden="true" />
  </span>
</template>

<style scoped>
.brand-mark {
  position: relative;
  display: inline-grid;
  place-items: center;
  background: var(--brand);
  color: var(--text-on-brand);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-inset);
  flex-shrink: 0;
}

.brand-mark__glyph {
  font-family: var(--font-display);
  font-weight: var(--fw-bold);
  font-size: calc(1em + 0.2em);
  line-height: 1;
  letter-spacing: -0.02em;
}

.brand-mark__dot {
  position: absolute;
  top: 22%;
  right: 22%;
  width: 18%;
  height: 18%;
  background: var(--text-on-brand);
  border-radius: 50%;
}
</style>
