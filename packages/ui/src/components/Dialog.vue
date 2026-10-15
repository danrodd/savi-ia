<script setup lang="ts">
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from 'reka-ui'

/**
 * Dialog primitivo y reutilizable basado en reka-ui (las primitivas
 * accesibles que están bajo shadcn-vue). Usa Teleport, focus trap,
 * lock de scroll del body y cierre con Esc/click en overlay.
 *
 * Estilos propios con CSS tokens — no depende de Tailwind.
 *
 * Uso:
 *   <Dialog v-model:open="open" title="Título" description="Texto">
 *     <p>Contenido libre…</p>
 *     <template #footer>
 *       <button @click="open = false">Cerrar</button>
 *     </template>
 *   </Dialog>
 */

withDefaults(
  defineProps<{
    open: boolean
    title?: string
    description?: string
    closeOnOverlay?: boolean
    maxWidth?: number
  }>(),
  {
    closeOnOverlay: true,
    maxWidth: 440,
  },
)
const emit = defineEmits<{ 'update:open': [value: boolean] }>()

function onUpdateOpen(value: boolean): void {
  emit('update:open', value)
}
</script>

<template>
  <DialogRoot :open="open" @update:open="onUpdateOpen">
    <DialogPortal>
      <DialogOverlay class="dialog-overlay" />
      <DialogContent
        class="dialog-content"
        :style="{ maxWidth: `${maxWidth}px` }"
        :trap-focus="true"
        @pointer-down-outside="(e) => !closeOnOverlay && e.preventDefault()"
      >
        <header v-if="title || $slots.header" class="dialog-header">
          <slot name="header">
            <div class="dialog-header__row">
              <slot name="leading" />
              <div>
                <DialogTitle class="dialog-title">{{ title }}</DialogTitle>
                <DialogDescription v-if="description" class="dialog-description">
                  {{ description }}
                </DialogDescription>
              </div>
            </div>
          </slot>
        </header>

        <div class="dialog-body">
          <slot />
        </div>

        <footer v-if="$slots.footer" class="dialog-footer">
          <slot name="footer" :close="() => onUpdateOpen(false)" />
        </footer>

        <DialogClose class="dialog-close" aria-label="Cerrar">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </DialogClose>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<style>
/*
 * Estilos NO scoped: reka-ui renderiza el contenido en un portal fuera
 * del componente, así que los selectores scoped no aplicarían.
 */
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 900;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(4px);
  animation: dialog-overlay-in 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}

.dialog-overlay[data-state='closed'] {
  animation: dialog-overlay-out 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}

.dialog-content {
  position: fixed;
  top: 50%;
  left: 50%;
  z-index: 950;
  width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  overflow: auto;
  padding: var(--space-7) var(--space-6) var(--space-6);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-lg);
  color: var(--text);
  font-family: var(--font-sans);
  transform: translate(-50%, -50%);
  animation: dialog-content-in 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}

.dialog-content[data-state='closed'] {
  animation: dialog-content-out 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}

.dialog-header {
  margin-bottom: var(--space-4);
}

.dialog-header__row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
}

.dialog-title {
  margin: 0 0 var(--space-2);
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: var(--fw-semibold);
  letter-spacing: -0.01em;
  line-height: 1.3;
  color: var(--text);
}

.dialog-description {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--text-muted);
}

.dialog-body {
  font-size: 14px;
  line-height: 1.55;
  color: var(--text);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  margin-top: var(--space-6);
}

.dialog-close {
  position: absolute;
  top: var(--space-4);
  right: var(--space-4);
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  color: var(--text-muted);
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out);
}

.dialog-close:hover,
.dialog-close:focus-visible {
  background: var(--surface-subtle);
  color: var(--text);
  border-color: var(--border);
  outline: none;
}

@keyframes dialog-overlay-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes dialog-overlay-out {
  from {
    opacity: 1;
  }
  to {
    opacity: 0;
  }
}

@keyframes dialog-content-in {
  from {
    opacity: 0;
    transform: translate(-50%, -48%) scale(0.96);
  }
  to {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
}

@keyframes dialog-content-out {
  from {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
  to {
    opacity: 0;
    transform: translate(-50%, -48%) scale(0.96);
  }
}
</style>
