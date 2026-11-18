<script setup lang="ts">
import { Tooltip, toast } from '@savi/ui'
import { Copy } from 'lucide-vue-next'
import { computed } from 'vue'

/**
 * Cómo se nombra a una persona en la consola. Con identidad `named`, su código de usuario.
 * Con seudónimo, "Persona N": un número estable que se puede decir en una llamada. El
 * seudónimo completo queda a mano (tooltip y copiar) para cruzarlo con soporte técnico.
 */
const props = defineProps<{
  userRef: string
  label?: string | null
  number?: number | null
}>()

const name = computed(() => {
  if (props.label) return props.label
  if (props.number) return `Persona ${props.number}`
  return `${props.userRef.slice(0, 8)}…`
})

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(props.userRef)
    toast.success('Seudónimo copiado')
  } catch {
    toast.error('No se pudo copiar el seudónimo')
  }
}
</script>

<template>
  <span class="person" data-test="person-label">
    <Tooltip :text="`Seudónimo: ${userRef}`">
      <strong tabindex="0">{{ name }}</strong>
    </Tooltip>
    <button
      v-if="!label"
      type="button"
      class="copy"
      :aria-label="`Copiar el seudónimo de ${name}`"
      data-test="person-copy"
      @click.stop="copy"
    >
      <Copy :size="13" aria-hidden="true" />
    </button>
  </span>
</template>

<style scoped>
.person {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}

.copy {
  display: inline-grid;
  place-items: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.copy:hover,
.copy:focus-visible {
  background: var(--surface-muted, var(--border));
  color: var(--text);
}
</style>
