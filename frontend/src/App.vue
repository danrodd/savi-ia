<script setup lang="ts"></script>

<template>
  <main class="savi-shell">
    <section class="savi-card">
      <p class="savi-eyebrow">SEO ERP</p>
      <h1 class="savi-title">SAVI</h1>
      <p class="savi-subtitle">Sistema de Asistente Virtual Inteligente</p>
    </section>
  </main>
</template>

<style scoped>
.savi-shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 2rem;
  background: var(--color-surface-alt);
  color: var(--color-text-strong);
  font-family: var(--font-body);
}

.savi-card {
  text-align: center;
  max-width: 32rem;
}

.savi-eyebrow {
  margin: 0 0 0.5rem;
  font-size: 0.875rem;
  letter-spacing: 0.25em;
  text-transform: uppercase;
  font-family: var(--font-display);
  font-weight: var(--font-weight-medium);
  color: var(--color-secondary);
}

.savi-title {
  margin: 0;
  font-size: clamp(3rem, 8vw, 5rem);
  font-family: var(--font-display);
  font-weight: var(--font-weight-semibold);
  letter-spacing: 0.05em;
  color: var(--color-primary);
}

.savi-subtitle {
  margin: 0.5rem 0 0;
  font-size: 1.125rem;
  font-family: var(--font-body);
  color: var(--color-text);
}
</style>
