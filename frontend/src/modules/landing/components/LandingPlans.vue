<script setup lang="ts">
import { Check } from 'lucide-vue-next'

import { PLANS } from '../content'
</script>

<template>
  <section id="planes" class="lp-section plans">
    <div class="lp-container">
      <p class="lp-eyebrow">Modelos de IA</p>
      <h2 class="lp-title">Elige cómo pagar la inteligencia artificial</h2>
      <p class="lp-lead">
        SAVI funciona con Claude, OpenAI o Gemini. Cambias de proveedor desde la administración, sin
        reinstalar nada.
      </p>
      <ul class="plans__grid">
        <li
          v-for="plan in PLANS"
          :key="plan.title"
          class="plans__card"
          :class="{ 'plans__card--soon': plan.badge }"
        >
          <div class="plans__head">
            <span class="plans__icon">
              <component :is="plan.icon" :size="20" aria-hidden="true" />
            </span>
            <span v-if="plan.badge" class="plans__badge">{{ plan.badge }}</span>
          </div>
          <h3>{{ plan.title }}</h3>
          <p>{{ plan.body }}</p>
          <ul class="plans__points">
            <li v-for="point in plan.points" :key="point">
              <Check :size="16" aria-hidden="true" />
              {{ point }}
            </li>
          </ul>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.plans__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin: 48px 0 0;
  padding: 0;
  list-style: none;
}

.plans__card {
  padding: 32px;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: var(--surface-elev);
}

.plans__card--soon {
  background: linear-gradient(
    160deg,
    color-mix(in srgb, var(--brand) 7%, var(--surface-elev)),
    var(--surface-elev) 60%
  );
}

.plans__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.plans__icon {
  display: inline-grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--brand-soft);
  color: var(--brand);
}

.plans__badge {
  padding: 4px 12px;
  border-radius: 999px;
  background: var(--brand);
  color: var(--text-on-brand);
  font-size: 12px;
  font-weight: var(--fw-semibold);
}

.plans__card h3 {
  margin: 20px 0 8px;
  font-family: var(--font-display);
  font-size: 21px;
  font-weight: var(--fw-semibold);
}

.plans__card > p {
  margin: 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--text-muted);
}

.plans__points {
  display: grid;
  gap: 10px;
  margin: 24px 0 0;
  padding: 0;
  list-style: none;
  font-size: 14px;
}

.plans__points li {
  display: flex;
  align-items: center;
  gap: 10px;
}

.plans__points svg {
  flex: none;
  color: var(--brand);
}

@media (max-width: 760px) {
  .plans__grid {
    grid-template-columns: 1fr;
  }

  .plans__card {
    padding: 24px;
  }
}
</style>
