<script setup lang="ts">
import { HIGHLIGHTS } from '../content'
import LandingChatMock from './LandingChatMock.vue'
</script>

<template>
  <section id="inicio" class="hero">
    <div class="hero__glow" aria-hidden="true" />
    <div class="lp-container hero__inner">
      <div class="hero__copy">
        <p class="lp-eyebrow">Asistente de IA para el ERP de SEO Group</p>
        <h1 class="hero__title">
          Pregúntale a tu empresa.
          <span class="hero__accent">SAVI responde con tus datos.</span>
        </h1>
        <p class="lp-lead">
          Ventas, cartera, documentos y tu sitio web en una sola conversación. Con cifras reales del
          ERP, fuentes citadas y los mismos permisos que ya usa tu equipo.
        </p>
        <div class="hero__actions">
          <a href="#demo" class="lp-button lp-button--primary">Solicitar demo</a>
          <a href="#que-hace" class="lp-button lp-button--ghost">Ver qué hace</a>
        </div>
        <ul class="hero__highlights">
          <li v-for="item in HIGHLIGHTS" :key="item.label">
            <component :is="item.icon" :size="16" aria-hidden="true" />
            {{ item.label }}
          </li>
        </ul>
      </div>
      <div class="hero__visual">
        <LandingChatMock />
      </div>
    </div>
  </section>
</template>

<style scoped>
.hero {
  position: relative;
  padding: 72px 0 96px;
}

.hero__glow {
  position: absolute;
  inset: -120px 0 auto;
  height: 620px;
  background:
    radial-gradient(40% 50% at 78% 30%, color-mix(in srgb, var(--brand) 16%, transparent), transparent 70%),
    radial-gradient(35% 40% at 15% 10%, color-mix(in srgb, var(--brand) 8%, transparent), transparent 70%);
  pointer-events: none;
}

.hero__inner {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
  align-items: center;
  gap: 56px;
}

.hero__title {
  margin: 0 0 20px;
  font-family: var(--font-display);
  font-size: clamp(36px, 5.4vw, 60px);
  font-weight: var(--fw-semibold);
  line-height: 1.05;
  letter-spacing: -0.02em;
}

.hero__accent {
  display: block;
  color: var(--brand);
}

.hero__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 32px;
}

.hero__highlights {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin: 32px 0 0;
  padding: 0;
  list-style: none;
  font-size: 13px;
  color: var(--text-muted);
}

.hero__highlights li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.hero__visual {
  animation: hero-float 7s ease-in-out infinite;
}

@keyframes hero-float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-8px);
  }
}

@media (max-width: 900px) {
  .hero {
    padding: 48px 0 64px;
  }

  .hero__inner {
    grid-template-columns: 1fr;
    gap: 40px;
  }
}
</style>
