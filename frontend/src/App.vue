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
  background: radial-gradient(circle at top, #1e293b, #0f172a);
  color: #f8fafc;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
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
  color: #94a3b8;
}

.savi-title {
  margin: 0;
  font-size: clamp(3rem, 8vw, 5rem);
  font-weight: 700;
  letter-spacing: 0.05em;
  background: linear-gradient(135deg, #38bdf8, #818cf8);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.savi-subtitle {
  margin: 0.5rem 0 0;
  font-size: 1.125rem;
  color: #cbd5e1;
}
</style>
