<script setup lang="ts">
import { STEPS } from '../content'
</script>

<template>
  <section id="como-funciona" class="lp-section how">
    <div class="lp-container">
      <p class="lp-eyebrow">Cómo funciona</p>
      <h2 class="lp-title">SAVI vive al lado de tu ERP, no en la nube de otro</h2>
      <p class="lp-lead">
        Se instala en un servidor de tu empresa y se conecta a la base del ERP que ya usas. SAVI Cloud
        (próximamente) solo administra licencias y mide el consumo: nunca ve tus datos.
      </p>

      <ol class="how__steps">
        <li v-for="(step, index) in STEPS" :key="step.title" class="how__step">
          <span class="how__number" aria-hidden="true">{{ index + 1 }}</span>
          <h3>{{ step.title }}</h3>
          <p>{{ step.body }}</p>
        </li>
      </ol>

      <div class="how__diagram" aria-hidden="true">
        <div class="how__zone">
          <p class="how__zone-label">Tu empresa</p>
          <div class="how__nodes">
            <span class="how__node">Usuarios · navegador</span>
            <span class="how__arrow">→</span>
            <span class="how__node how__node--brand">SAVI Servidor</span>
            <span class="how__arrow">→</span>
            <span class="how__node">Base del ERP</span>
          </div>
        </div>
        <div class="how__cloud">
          <span class="how__arrow how__arrow--up">↕</span>
          <span class="how__node how__node--muted">SAVI Cloud · métricas y licencias</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.how {
  background: var(--surface-sidebar);
}

.how__steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 32px;
  margin: 48px 0 0;
  padding: 0;
  list-style: none;
}

.how__number {
  display: inline-grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--brand);
  color: var(--text-on-brand);
  font-family: var(--font-display);
  font-weight: var(--fw-semibold);
}

.how__step h3 {
  margin: 16px 0 8px;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: var(--fw-semibold);
}

.how__step p {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--text-muted);
}

.how__diagram {
  display: grid;
  justify-items: center;
  gap: 12px;
  margin-top: 56px;
}

.how__zone {
  width: 100%;
  padding: 20px;
  border: 1.5px dashed color-mix(in srgb, var(--brand) 40%, var(--border));
  border-radius: 20px;
  background: var(--surface-elev);
}

.how__zone-label {
  margin: 0 0 12px;
  font-size: 12px;
  font-weight: var(--fw-semibold);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.how__nodes {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.how__node {
  padding: 10px 18px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  font-size: 14px;
  font-weight: var(--fw-medium);
}

.how__node--brand {
  border-color: var(--brand);
  background: var(--brand);
  color: var(--text-on-brand);
}

.how__node--muted {
  border-style: dashed;
  color: var(--text-muted);
}

.how__arrow {
  color: var(--text-subtle);
  font-size: 18px;
}

.how__cloud {
  display: grid;
  justify-items: center;
  gap: 8px;
}

@media (max-width: 820px) {
  .how__steps {
    grid-template-columns: 1fr;
    gap: 24px;
  }

  .how__nodes {
    flex-direction: column;
  }

  .how__nodes .how__arrow {
    transform: rotate(90deg);
  }
}
</style>
