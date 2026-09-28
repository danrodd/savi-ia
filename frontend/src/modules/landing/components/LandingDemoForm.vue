<script setup lang="ts">
/**
 * "Solicitar demo". Sin backend público todavía: valida y abre el correo
 * con todo completo, dirigido a `VITE_LANDING_CONTACT_EMAIL`.
 */
import { reactive, ref } from 'vue'

import { ENV } from '@/lib/env'
import { type DemoRequest, demoMailto, validateDemoRequest } from '../utils/demoRequest'

const form = reactive<Required<DemoRequest>>({
  name: '',
  company: '',
  email: '',
  phone: '',
  message: '',
})
const errors = ref<Partial<Record<keyof DemoRequest, string>>>({})
const sent = ref(false)
const contact = ENV.LANDING_CONTACT_EMAIL

function onSubmit(): void {
  const result = validateDemoRequest(form)
  errors.value = result.errors
  if (!result.ok) return
  const link = demoMailto(form, contact)
  if (!link) return
  window.location.href = link
  sent.value = true
}
</script>

<template>
  <section id="demo" class="lp-section demo">
    <div class="lp-container demo__inner">
      <div class="demo__copy">
        <p class="lp-eyebrow">Solicitar demo</p>
        <h2 class="lp-title">Mira SAVI con los datos de tu empresa</h2>
        <p class="lp-lead">
          Te mostramos cómo responde sobre tu ERP, tus documentos y tu sitio web. Sin compromiso.
        </p>
      </div>

      <form class="demo__form" novalidate @submit.prevent="onSubmit">
        <label class="demo__field">
          <span>Nombre</span>
          <input v-model="form.name" autocomplete="name" :aria-invalid="!!errors.name" />
          <small v-if="errors.name" role="alert">{{ errors.name }}</small>
        </label>
        <label class="demo__field">
          <span>Empresa</span>
          <input
            v-model="form.company"
            autocomplete="organization"
            :aria-invalid="!!errors.company"
          />
          <small v-if="errors.company" role="alert">{{ errors.company }}</small>
        </label>
        <label class="demo__field">
          <span>Correo</span>
          <input
            v-model="form.email"
            type="email"
            autocomplete="email"
            :aria-invalid="!!errors.email"
          />
          <small v-if="errors.email" role="alert">{{ errors.email }}</small>
        </label>
        <label class="demo__field">
          <span>Teléfono <em>(opcional)</em></span>
          <input v-model="form.phone" type="tel" autocomplete="tel" />
        </label>
        <label class="demo__field demo__field--wide">
          <span>¿Qué te gustaría resolver? <em>(opcional)</em></span>
          <textarea v-model="form.message" rows="3" maxlength="1000" />
        </label>

        <p v-if="!contact" class="demo__note" role="status">
          El formulario todavía no tiene un correo de destino configurado.
        </p>
        <p v-else-if="sent" class="demo__note" role="status">
          Se abrió tu correo con la solicitud lista. Solo falta enviarla.
        </p>
        <button type="submit" class="lp-button lp-button--primary demo__submit" :disabled="!contact">
          Solicitar demo
        </button>
      </form>
    </div>
  </section>
</template>

<style scoped>
.demo__inner {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: 56px;
  align-items: start;
}

.demo__form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  padding: 32px;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: var(--surface-elev);
  box-shadow: var(--shadow-md);
}

.demo__field {
  display: grid;
  gap: 6px;
  font-size: 13px;
  font-weight: var(--fw-medium);
}

.demo__field em {
  font-style: normal;
  font-weight: normal;
  color: var(--text-subtle);
}

.demo__field--wide {
  grid-column: 1 / -1;
}

.demo__field input,
.demo__field textarea {
  width: 100%;
  padding: 11px 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  color: var(--text);
  font: inherit;
  font-size: 15px;
  font-weight: normal;
  resize: vertical;
}

.demo__field input:focus-visible,
.demo__field textarea:focus-visible {
  outline: 2px solid var(--brand-ring);
  outline-offset: 1px;
  border-color: var(--brand);
}

.demo__field input[aria-invalid='true'] {
  border-color: var(--text-danger);
}

.demo__field small {
  font-weight: normal;
  color: var(--text-danger);
}

.demo__note {
  grid-column: 1 / -1;
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
}

.demo__submit {
  grid-column: 1 / -1;
  justify-self: start;
}

.demo__submit:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

@media (max-width: 860px) {
  .demo__inner {
    grid-template-columns: 1fr;
    gap: 32px;
  }

  .demo__form {
    grid-template-columns: 1fr;
    padding: 22px;
  }
}
</style>
