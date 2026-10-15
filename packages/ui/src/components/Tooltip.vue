<script setup lang="ts">
import {
  TooltipArrow,
  TooltipContent,
  TooltipPortal,
  TooltipProvider,
  TooltipRoot,
  TooltipTrigger,
} from 'reka-ui'

/**
 * Tooltip reutilizable basado en reka-ui. Pensado para botones icon-only.
 *
 * Uso:
 *   <Tooltip text="Enviar">
 *     <button>…</button>
 *   </Tooltip>
 */

withDefaults(
  defineProps<{
    text: string
    side?: 'top' | 'right' | 'bottom' | 'left'
    delay?: number
  }>(),
  {
    side: 'top',
    delay: 300,
  },
)
</script>

<template>
  <TooltipProvider :delay-duration="delay">
    <TooltipRoot>
      <TooltipTrigger as-child>
        <slot />
      </TooltipTrigger>
      <TooltipPortal>
        <TooltipContent :side="side" :side-offset="6" class="tooltip-content">
          {{ text }}
          <TooltipArrow class="tooltip-arrow" :width="10" :height="5" />
        </TooltipContent>
      </TooltipPortal>
    </TooltipRoot>
  </TooltipProvider>
</template>

<style>
.tooltip-content {
  z-index: 1100;
  padding: var(--space-2) var(--space-3);
  background: var(--surface-inverse);
  color: var(--surface);
  border-radius: var(--r-sm);
  font-family: var(--font-sans);
  font-size: 12px;
  font-weight: var(--fw-medium);
  line-height: 1.3;
  box-shadow: var(--shadow-md);
  user-select: none;
  animation: tooltip-in 0.12s cubic-bezier(0.4, 0, 0.2, 1);
}

.tooltip-arrow {
  fill: var(--surface-inverse);
}

@keyframes tooltip-in {
  from {
    opacity: 0;
    transform: scale(0.94);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
</style>
