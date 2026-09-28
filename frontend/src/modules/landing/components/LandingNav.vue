<script setup lang="ts">
import { RouterLink } from 'vue-router'

const LINKS = [
  { href: '#que-hace', label: 'Qué hace' },
  { href: '#como-funciona', label: 'Cómo funciona' },
  { href: '#seguridad', label: 'Seguridad' },
  { href: '#planes', label: 'Planes' },
] as const
</script>

<template>
  <header class="lnav">
    <div class="lp-container lnav__inner">
      <a href="#inicio" class="lnav__brand" aria-label="SAVI, ir al inicio">
        <img src="/savi-mark.png" alt="" width="32" height="32" />
        <span>SAVI</span>
      </a>
      <nav class="lnav__links" aria-label="Secciones">
        <a v-for="link in LINKS" :key="link.href" :href="link.href">{{ link.label }}</a>
      </nav>
      <div class="lnav__actions">
        <RouterLink :to="{ name: 'login' }" class="lnav__login">Iniciar sesión</RouterLink>
        <a href="#demo" class="lp-button lp-button--primary lnav__cta">Solicitar demo</a>
      </div>
    </div>
  </header>
</template>

<style scoped>
.lnav {
  position: sticky;
  top: 0;
  z-index: 20;
  background: color-mix(in srgb, var(--surface) 82%, transparent);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
}

.lnav__inner {
  display: flex;
  align-items: center;
  gap: 24px;
  height: 64px;
}

.lnav__brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: var(--fw-semibold);
  color: var(--text);
  text-decoration: none;
}

.lnav__brand img {
  border-radius: 8px;
}

.lnav__links {
  display: flex;
  gap: 24px;
  margin-left: 16px;
}

.lnav__links a,
.lnav__login {
  font-size: 14px;
  color: var(--text-muted);
  text-decoration: none;
}

.lnav__links a:hover,
.lnav__login:hover {
  color: var(--text);
}

.lnav__actions {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-left: auto;
}

.lnav__cta {
  height: 38px;
  padding: 0 16px;
  font-size: 14px;
}

@media (max-width: 860px) {
  .lnav__links {
    display: none;
  }
}

@media (max-width: 420px) {
  .lnav__login {
    display: none;
  }
}
</style>
