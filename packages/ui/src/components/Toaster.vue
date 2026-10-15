<script setup lang="ts">
import { Toaster } from 'vue-sonner'
import 'vue-sonner/style.css'

/**
 * Punto único de montaje de los toasts (vue-sonner). Va una sola vez en
 * App.vue. Los toasts se disparan desde cualquier parte con el helper
 * `toast` de '@/lib/toast'.
 */
</script>

<template>
  <Toaster
    position="bottom-right"
    :duration="3500"
    :gap="10"
    :offset="16"
    close-button
    :toast-options="{ class: 'savi-toast' }"
  />
</template>

<style>
:where([data-sonner-toaster]) {
  --normal-bg: var(--surface-elev);
  --normal-text: var(--text);
  --normal-border: var(--border);
  font-family: var(--font-sans);
}

:where([data-sonner-toast]) {
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-lg);
  color: var(--text);
}

:where([data-sonner-toast]) [data-title] {
  font-size: 13.5px;
  font-weight: var(--fw-medium);
  color: var(--text);
}

:where([data-sonner-toast]) [data-description] {
  font-size: 12.5px;
  color: var(--text-muted);
}

:where([data-sonner-toast][data-type='success']) [data-icon] {
  color: var(--success);
}

:where([data-sonner-toast][data-type='error']) [data-icon] {
  color: var(--brand);
}

:where([data-sonner-toast]) [data-close-button] {
  background: var(--surface-elev);
  border: 1px solid var(--border);
  color: var(--text-muted);
}

:where([data-sonner-toast]) [data-close-button]:hover {
  background: var(--surface-subtle);
  color: var(--text);
}
</style>
