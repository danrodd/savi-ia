<script setup lang="ts">
/**
 * Placeholder de carga con shimmer. Reutilizable para listas, cards, texto.
 *
 * Uso:
 *   <Skeleton width="60%" height="14px" />
 *   <Skeleton :rounded="true" width="32px" height="32px" />
 */

withDefaults(
  defineProps<{
    width?: string
    height?: string
    rounded?: boolean
    radius?: string
  }>(),
  {
    width: '100%',
    height: '1em',
    rounded: false,
  },
)
</script>

<template>
  <span
    class="skeleton"
    :class="{ 'skeleton--circle': rounded }"
    :style="{ width, height, borderRadius: rounded ? '50%' : radius }"
    aria-hidden="true"
  />
</template>

<style scoped>
.skeleton {
  display: inline-block;
  background: linear-gradient(
    90deg,
    var(--surface-subtle) 25%,
    var(--surface-hover) 37%,
    var(--surface-subtle) 63%
  );
  background-size: 400% 100%;
  border-radius: var(--r-sm);
  animation: skeleton-shimmer 1.4s ease infinite;
}

@keyframes skeleton-shimmer {
  0% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0 50%;
  }
}
</style>
