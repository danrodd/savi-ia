<script setup lang="ts">
/**
 * SecurityView — seguridad de la instalación.
 *
 * Hoy: restablecer el segundo factor de una persona que perdió su celular. Al restablecerlo se
 * cierran sus sesiones y en el próximo ingreso configura una aplicación nueva.
 */
import { computed, ref } from 'vue'

import Button from '@/components/ui/Button.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import { toast } from '@/lib/toast'
import { mfaAdminService } from '../services/mfaAdminService'

const login = ref('')
const confirmOpen = ref(false)
const clean = computed(() => login.value.trim())

async function onReset(): Promise<void> {
  try {
    const { reset } = await mfaAdminService.reset(clean.value)
    if (reset) {
      toast.success(`Se restablecieron los dos pasos de ${clean.value}. Sus sesiones se cerraron.`)
      login.value = ''
    } else {
      toast.info(`${clean.value} no tenía la verificación en dos pasos configurada.`)
    }
  } catch (e) {
    toast.error((e as Error).message)
    throw e
  }
}
</script>

<template>
  <section class="sec" data-testid="security-view">
    <header class="sec__header">
      <h1 class="sec__title">Seguridad</h1>
      <p class="sec__subtitle">
        Los administradores de SAVI confirman su ingreso con un código de su aplicación de
        autenticación.
      </p>
    </header>

    <section class="sec__card">
      <h2 class="sec__h2">Restablecer la verificación en dos pasos</h2>
      <p class="sec__text">
        Para quien perdió o cambió el celular. Se cierran sus sesiones y en el próximo ingreso
        configura la aplicación de nuevo.
      </p>
      <form class="sec__form" @submit.prevent="confirmOpen = true">
        <label class="sec__field">
          <span>Usuario</span>
          <input
            v-model="login"
            type="text"
            autocomplete="off"
            spellcheck="false"
            placeholder="USUARIO@CODIGO"
            data-testid="mfa-reset-login"
          >
          <small>Con el código del cliente si atendés varios: <code>USUARIO@CODIGO</code>.</small>
        </label>
        <div>
          <Button type="submit" :disabled="!clean" variant="secondary">Restablecer</Button>
        </div>
      </form>
    </section>

    <ConfirmDialog
      v-model:open="confirmOpen"
      title="Restablecer la verificación en dos pasos"
      :description="`${clean} va a tener que configurar su aplicación de autenticación de nuevo y se le cierran las sesiones abiertas.`"
      confirm-label="Restablecer"
      variant="danger"
      :on-confirm="onReset"
    />
  </section>
</template>

<style scoped>
.sec {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.sec__title {
  margin: 0;
  font-size: 20px;
}

.sec__subtitle,
.sec__text {
  margin: var(--space-2) 0 0;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.5;
}

.sec__card {
  padding: var(--space-6);
  background: var(--surface-elev);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
}

.sec__h2 {
  margin: 0;
  font-size: 15px;
}

.sec__form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin-top: var(--space-4);
  max-width: 420px;
}

.sec__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  font-size: 13px;
}

.sec__field input {
  height: 38px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  background: var(--surface);
  color: var(--text);
  font-family: inherit;
}

.sec__field small {
  color: var(--text-subtle);
}
</style>
