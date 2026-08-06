<script setup lang="ts">
/**
 * Pantalla de bienvenida del chat.
 *
 * Personaliza el saludo con el nombre del usuario y muestra pines
 * clickeables con preguntas sugeridas según los módulos activos.
 * Si el usuario es admin → ve sugerencias de todo el catálogo.
 * Si tiene módulos limitados → solo sugerencias de esos módulos +
 * generales como relleno.
 *
 * Click en un pin → emite `suggest` con el prompt; el padre lo manda
 * por el flujo normal de envío.
 */
import BrandMark from './BrandMark.vue'
import { useWelcome } from '../composables/useWelcome'

defineEmits<{
  suggest: [text: string]
}>()

const { greeting, subtitle, suggestions, reshuffle } = useWelcome()
</script>

<template>
  <div class="welcome">
    <div class="welcome__inner">
      <BrandMark :size="64" class="welcome__mark" />
      <p class="welcome__eyebrow">Asistente del ERP</p>
      <h1 class="welcome__title">{{ greeting }}</h1>
      <p class="welcome__subtitle">{{ subtitle }}</p>

      <div v-if="suggestions.length > 0" class="welcome__suggestions">
        <div class="welcome__suggestions-head">
          <h2 class="welcome__suggestions-title">Probá con alguna de estas</h2>
          <button
            type="button"
            class="welcome__refresh"
            aria-label="Mostrar otras sugerencias"
            @click="reshuffle"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
              aria-hidden="true"
            >
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
            Otras
          </button>
        </div>
        <ul class="welcome__grid" aria-label="Sugerencias de preguntas">
          <li v-for="(s, i) in suggestions" :key="`${s.prompt}-${i}`">
            <button
              type="button"
              class="welcome__card"
              @click="$emit('suggest', s.prompt)"
            >
              <span v-if="s.moduleLabel" class="welcome__chip">{{ s.moduleLabel }}</span>
              <span class="welcome__card-text">{{ s.label }}</span>
            </button>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<style scoped>
.welcome {
  flex: 1;
  min-height: 0;
  display: grid;
  place-items: center;
  padding: var(--space-7) var(--space-5);
  overflow-y: auto;
}

.welcome__inner {
  max-width: 720px;
  width: 100%;
  text-align: center;
}

.welcome__mark {
  margin: 0 auto var(--space-5);
  box-shadow: var(--shadow-brand);
}

.welcome__mark :deep(.brand-mark__glyph) {
  font-size: 36px;
}

.welcome__eyebrow {
  margin: 0 0 var(--space-2);
  font-size: 10.5px;
  font-weight: var(--fw-semibold);
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--text-subtle);
}

.welcome__title {
  margin: 0 0 var(--space-3);
  font-family: var(--font-display);
  font-size: clamp(26px, 5.5vw, 36px);
  font-weight: var(--fw-semibold);
  letter-spacing: -0.02em;
  color: var(--text);
  line-height: 1.15;
}

.welcome__subtitle {
  margin: 0 auto var(--space-6);
  max-width: 540px;
  font-size: 14.5px;
  line-height: 1.55;
  color: var(--text-muted);
}

.welcome__suggestions {
  width: 100%;
  margin-top: var(--space-2);
  text-align: left;
}

.welcome__suggestions-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  padding: 0 var(--space-1);
}

.welcome__suggestions-title {
  margin: 0;
  font-size: 11px;
  font-weight: var(--fw-medium);
  color: var(--text-subtle);
  text-transform: uppercase;
  letter-spacing: 0.12em;
}

.welcome__refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  font-size: 11px;
  font-weight: var(--fw-medium);
  letter-spacing: 0.04em;
  color: var(--text-muted);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
}

.welcome__refresh:hover {
  background: var(--surface-hover);
  color: var(--text);
  border-color: var(--border-strong);
}

.welcome__grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--space-3);
}

.welcome__card {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  min-height: 84px;
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
  box-shadow: var(--shadow-xs);
}

.welcome__card:hover {
  background: var(--surface-hover);
  border-color: var(--border-strong);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.welcome__card:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 2px;
}

.welcome__chip {
  display: inline-block;
  padding: 2px 8px;
  background: var(--surface-subtle);
  color: var(--text-subtle);
  border-radius: 999px;
  font-size: 10px;
  font-weight: var(--fw-medium);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.welcome__card-text {
  font-size: 13.5px;
  line-height: 1.4;
  color: var(--text);
  font-weight: var(--fw-regular);
}

@media (max-width: 767px) {
  .welcome {
    padding: var(--space-5);
  }

  .welcome__mark {
    width: 56px !important;
    height: 56px !important;
    margin-bottom: var(--space-4);
  }

  .welcome__grid {
    grid-template-columns: 1fr;
  }
}
</style>
