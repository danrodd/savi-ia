<script setup lang="ts">
import { FEATURES, VERTICALS } from '../content'
</script>

<template>
  <section id="que-hace" class="lp-section features">
    <div class="lp-container">
      <p class="lp-eyebrow">Qué hace</p>
      <h2 class="lp-title">Todo lo que tu empresa sabe, en una conversación</h2>
      <p class="lp-lead">
        Tu equipo deja de buscar entre reportes, carpetas y páginas. Pregunta como le preguntaría a un
        compañero y recibe la respuesta con su fuente.
      </p>

      <ul class="features__grid">
        <li v-for="feature in FEATURES" :key="feature.title" class="features__card">
          <span class="features__icon">
            <component :is="feature.icon" :size="20" aria-hidden="true" />
          </span>
          <h3>{{ feature.title }}</h3>
          <p>{{ feature.body }}</p>
          <p class="features__example">“{{ feature.example }}”</p>
        </li>
      </ul>

      <div class="features__verticals">
        <p>Para todos los verticales del ERP</p>
        <ul>
          <li v-for="vertical in VERTICALS" :key="vertical">{{ vertical }}</li>
        </ul>
      </div>
    </div>
  </section>
</template>

<style scoped>
.features__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin: 48px 0 0;
  padding: 0;
  list-style: none;
}

.features__card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 28px;
  border: 1px solid var(--border);
  border-radius: 18px;
  background: var(--surface-elev);
  transition:
    border-color var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out);
}

.features__card:hover {
  border-color: color-mix(in srgb, var(--brand) 35%, var(--border));
  transform: translateY(-2px);
}

.features__icon {
  display: inline-grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--brand-soft);
  color: var(--brand);
}

.features__card h3 {
  margin: 6px 0 0;
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: var(--fw-semibold);
}

.features__card p {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--text-muted);
}

.features__card .features__example {
  margin-top: auto;
  padding-top: 12px;
  font-family: var(--font-serif);
  font-size: 17px;
  font-style: italic;
  color: var(--text);
}

.features__verticals {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 20px;
  margin-top: 40px;
}

.features__verticals p {
  margin: 0;
  font-size: 14px;
  color: var(--text-muted);
}

.features__verticals ul {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.features__verticals li {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 13px;
}

@media (max-width: 760px) {
  .features__grid {
    grid-template-columns: 1fr;
  }

  .features__card {
    padding: 22px;
  }
}
</style>
