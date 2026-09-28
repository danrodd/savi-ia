<script setup lang="ts">
const year = new Date().getFullYear()
</script>

<template>
  <footer class="lfoot">
    <div class="lp-container lfoot__inner">
      <div class="lfoot__brand">
        <img src="/savi-mark.png" alt="" width="28" height="28" />
        <div>
          <p class="lfoot__name">SAVI</p>
          <p class="lfoot__tag">S.E.O. Asistente Virtual Inteligente</p>
        </div>
      </div>
      <p class="lfoot__copy">© {{ year }} SEO Group. Todos los derechos reservados.</p>
    </div>
  </footer>
</template>

<style scoped>
.lfoot {
  padding: 32px 0;
  border-top: 1px solid var(--border);
}

.lfoot__inner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.lfoot__brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.lfoot__brand img {
  border-radius: 7px;
}

.lfoot__name {
  margin: 0;
  font-family: var(--font-display);
  font-weight: var(--fw-semibold);
}

.lfoot__tag,
.lfoot__copy {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
}
</style>
