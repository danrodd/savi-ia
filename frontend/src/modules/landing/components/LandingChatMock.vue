<script setup lang="ts">
/**
 * Muestra del chat para la portada. Datos inventados a propósito: una
 * captura real traería nombres y cifras de un cliente.
 */
const ROWS = [
  { month: 'Febrero', amount: '$ 412,8 M', change: '' },
  { month: 'Marzo', amount: '$ 468,3 M', change: '+13,4 %' },
] as const
</script>

<template>
  <div class="mock" aria-label="Ejemplo de conversación con SAVI" role="img">
    <div class="mock__bar" aria-hidden="true">
      <span /><span /><span />
      <p>SAVI · Distribuidora Andes</p>
    </div>
    <div class="mock__body" aria-hidden="true">
      <p class="mock__question">¿Cuánto facturamos en marzo frente a febrero?</p>
      <div class="mock__answer">
        <img src="/savi-mark.png" alt="" width="28" height="28" class="mock__avatar" />
        <div class="mock__content">
          <p class="mock__tool">✓ Consultó ventas del ERP</p>
          <p>
            En marzo facturaron <strong>$ 468,3 millones</strong>, un
            <strong>13,4 % más</strong> que en febrero.
          </p>
          <table class="mock__table">
            <thead>
              <tr>
                <th>Mes</th>
                <th>Facturado</th>
                <th>Variación</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in ROWS" :key="row.month">
                <td>{{ row.month }}</td>
                <td>{{ row.amount }}</td>
                <td class="mock__up">{{ row.change }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <p class="mock__question">¿Y hasta qué descuento puedo dar sin autorización?</p>
      <div class="mock__answer">
        <img src="/savi-mark.png" alt="" width="28" height="28" class="mock__avatar" />
        <div class="mock__content">
          <p>Hasta el <strong>8 %</strong>. Por encima, lo autoriza la dirección comercial.¹</p>
          <p class="mock__source">¹ Política comercial 2026 · p. 3</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mock {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 18px;
  background: var(--surface-elev);
  box-shadow:
    0 30px 60px -20px rgba(0, 0, 0, 0.18),
    0 0 0 1px color-mix(in srgb, var(--brand) 6%, transparent);
  font-size: 13px;
  text-align: left;
}

.mock__bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-sidebar);
}

.mock__bar span {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--surface-hover);
}

.mock__bar p {
  margin: 0 0 0 8px;
  font-size: 12px;
  color: var(--text-muted);
}

.mock__body {
  display: grid;
  gap: 14px;
  padding: 18px;
}

.mock__question {
  justify-self: end;
  max-width: 85%;
  margin: 0;
  padding: 9px 14px;
  border-radius: 14px;
  background: var(--surface-subtle);
}

.mock__answer {
  display: flex;
  gap: 10px;
}

.mock__avatar {
  flex: none;
  border-radius: 7px;
}

.mock__content {
  display: grid;
  gap: 8px;
  min-width: 0;
  line-height: 1.5;
}

.mock__content p {
  margin: 0;
}

.mock__tool {
  justify-self: start;
  padding: 2px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 11px;
  color: var(--text-muted);
}

.mock__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.mock__table th,
.mock__table td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: left;
}

.mock__table th {
  font-weight: var(--fw-medium);
  color: var(--text-muted);
}

.mock__up {
  color: var(--text-success, #15803d);
  font-weight: var(--fw-medium);
}

.mock__source {
  padding-top: 6px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-muted);
}
</style>
