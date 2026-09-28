<script setup lang="ts">
import { SECURITY } from '../content'
</script>

<template>
  <section id="seguridad" class="lp-section security">
    <div class="lp-container">
      <p class="lp-eyebrow security__eyebrow">Seguridad y privacidad</p>
      <h2 class="lp-title security__title">
        Diseñado para que la información de tu empresa se quede en tu empresa
      </h2>
      <ul class="security__grid">
        <li v-for="pillar in SECURITY" :key="pillar.title">
          <component :is="pillar.icon" :size="22" aria-hidden="true" class="security__icon" />
          <h3>{{ pillar.title }}</h3>
          <p>{{ pillar.body }}</p>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.security {
  background: var(--surface-inverse);
  color: var(--surface);
}

.security__eyebrow {
  color: color-mix(in srgb, var(--brand) 70%, #ffffff);
}

.security__title {
  color: var(--surface);
}

.security__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 24px;
  margin: 48px 0 0;
  padding: 0;
  list-style: none;
}

.security__grid li {
  padding-top: 20px;
  border-top: 1px solid color-mix(in srgb, var(--surface) 20%, transparent);
}

.security__icon {
  color: color-mix(in srgb, var(--brand) 70%, #ffffff);
}

.security__grid h3 {
  margin: 14px 0 8px;
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: var(--fw-semibold);
}

.security__grid p {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: color-mix(in srgb, var(--surface) 70%, transparent);
}

@media (max-width: 900px) {
  .security__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .security__grid {
    grid-template-columns: 1fr;
  }
}
</style>
