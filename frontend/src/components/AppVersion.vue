<script setup lang="ts">
/**
 * Versión de SAVI en texto chico, siempre visible.
 *
 * Es lo primero que pregunta soporte. El número es el tag de git
 * incrustado en el build (ver `vite.config.ts`), así que coincide con lo
 * que devuelve `GET /version` del backend del mismo instalador.
 */
const version = __APP_VERSION__
</script>

<template>
  <p class="app-version" :title="`SAVI ${version}`">SAVI {{ version }}</p>
</template>

<style scoped>
.app-version {
  margin: 0;
  padding: 0 var(--space-3);
  font-family: var(--font-mono, monospace);
  font-size: 10.5px;
  color: var(--text-subtle);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  user-select: all;
}
</style>
