<script setup lang="ts">
/**
 * Landing pública de SAVI (`/inicio`). Solo compone secciones: los textos
 * viven en `content.ts` y cada sección en su componente.
 */
import '../landing.css'

import { onMounted } from 'vue'

import LandingDemoForm from '../components/LandingDemoForm.vue'
import LandingFeatures from '../components/LandingFeatures.vue'
import LandingFooter from '../components/LandingFooter.vue'
import LandingHero from '../components/LandingHero.vue'
import LandingHowItWorks from '../components/LandingHowItWorks.vue'
import LandingNav from '../components/LandingNav.vue'
import LandingPlans from '../components/LandingPlans.vue'
import LandingSecurity from '../components/LandingSecurity.vue'

onMounted(() => {
  document.title = 'SAVI · Asistente de IA para tu ERP'
})
</script>

<template>
  <div class="lp">
    <LandingNav />
    <main>
      <LandingHero />
      <LandingFeatures />
      <LandingHowItWorks />
      <LandingSecurity />
      <LandingPlans />
      <LandingDemoForm />
    </main>
    <LandingFooter />
  </div>
</template>
