<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 28 })
</script>

<template>
  <img
    class="brand-mark"
    src="/savi-mark.png"
    alt="SAVI"
    :width="size"
    :height="size"
    :style="{ width: `${size}px`, height: `${size}px` }"
  >
</template>

<style scoped>
.brand-mark {
  display: block;
  object-fit: cover;
  border-radius: var(--r-md);
  box-shadow: var(--shadow-inset);
  flex-shrink: 0;
}
</style>
