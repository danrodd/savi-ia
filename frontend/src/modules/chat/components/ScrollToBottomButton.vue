<script setup lang="ts">
import { computed } from 'vue'
import BrandMark from './BrandMark.vue'

const props = defineProps<{
  /** Hay contenido nuevo del stream por debajo del viewport. */
  hasNew: boolean
  /** El asistente todavía está generando (stream en curso). */
  streaming: boolean
}>()
defineEmits<{ click: [] }>()

const label = computed(() => (props.streaming ? 'SAVI respondiendo' : 'Ver respuesta'))
const ariaLabel = computed(() =>
  props.hasNew
    ? `${label.value} — bajar al final de la conversación`
    : 'Bajar al final de la conversación',
)
</script>

<template>
  <!-- Pill con identidad SAVI: aparece cuando llegó/llega contenido nuevo
       mientras el usuario está arriba. Distingue "respondiendo…" de "completo". -->
  <button
    v-if="hasNew"
    type="button"
    class="scroll-pill"
    :class="{ 'scroll-pill--streaming': streaming }"
    :aria-label="ariaLabel"
    @click="$emit('click')"
  >
    <BrandMark :size="22" class="scroll-pill__mark" />
    <span class="scroll-pill__label">
      {{ label }}<span v-if="streaming" class="scroll-pill__ellipsis" aria-hidden="true" />
    </span>
    <svg
      class="scroll-pill__arrow"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2.5"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  </button>

  <!-- Estado compacto: el usuario scrolleó arriba pero no hay novedad. -->
  <button
    v-else
    type="button"
    class="scroll-circle"
    :aria-label="ariaLabel"
    @click="$emit('click')"
  >
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2.5"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  </button>
</template>

<style scoped>
/* ---- Estado compacto (círculo) ---- */
.scroll-circle {
  display: inline-grid;
  place-items: center;
  width: 40px;
  height: 40px;
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-pill);
  color: var(--text-muted);
  box-shadow: var(--shadow-md);
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out);
}

.scroll-circle:hover {
  background: var(--surface-hover);
  color: var(--text);
  transform: translateY(-1px);
}

.scroll-circle:active {
  transform: translateY(0);
}

/* ---- Estado con novedad (pill SAVI) ---- */
.scroll-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  height: 40px;
  padding: 0 var(--space-3) 0 var(--space-2);
  background: var(--surface-elev);
  border: 1px solid var(--brand);
  border-radius: var(--r-pill);
  color: var(--text);
  box-shadow: var(--shadow-lg);
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out);
}

.scroll-pill:hover {
  background: var(--surface-hover);
  transform: translateY(-1px);
}

.scroll-pill:active {
  transform: translateY(0);
}

.scroll-pill__mark {
  box-shadow: var(--shadow-inset);
}

/* Latido sutil del glifo mientras SAVI sigue generando. */
.scroll-pill--streaming .scroll-pill__mark {
  animation: scroll-pill-beat 1.4s var(--ease-out) infinite;
}

.scroll-pill__label {
  font-size: 13.5px;
  font-weight: var(--fw-medium);
  letter-spacing: -0.005em;
  white-space: nowrap;
}

/* Puntos suspensivos animados durante el stream ("respondiendo…"). */
.scroll-pill__ellipsis::after {
  content: '…';
  display: inline-block;
  width: 1ch;
  animation: scroll-pill-dots 1.4s steps(4, end) infinite;
}

.scroll-pill__arrow {
  color: var(--brand);
  flex-shrink: 0;
}

@keyframes scroll-pill-beat {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.08);
  }
}

@keyframes scroll-pill-dots {
  0% {
    clip-path: inset(0 100% 0 0);
  }
  100% {
    clip-path: inset(0 0 0 0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .scroll-circle,
  .scroll-circle:hover,
  .scroll-circle:active,
  .scroll-pill,
  .scroll-pill:hover,
  .scroll-pill:active {
    transition: none;
    transform: none;
  }

  .scroll-pill--streaming .scroll-pill__mark,
  .scroll-pill__ellipsis::after {
    animation: none;
  }

  .scroll-pill__ellipsis::after {
    clip-path: none;
  }
}
</style>
