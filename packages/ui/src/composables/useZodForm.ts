import { computed, reactive, ref, type UnwrapRef, watch } from 'vue'
import type { z } from 'zod'

type Errors = Record<string, string | undefined>

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

/**
 * Estado de un formulario validado con zod.
 *
 * - `values` es reactivo y se enlaza con `v-model`.
 * - `errors` solo muestra el error de un campo después de tocarlo (`touch`,
 *   normalmente en `@blur`) o de intentar enviar: nadie quiere ver "obligatorio"
 *   antes de escribir.
 * - `setServerErrors` pone en los campos los errores que devolvió el backend;
 *   se borran al volver a editar.
 * - `isDirty` compara contra el último estado guardado (`reset`).
 *
 * La clave de cada error es la ruta del campo unida con puntos (`limits.monthly`).
 */
export function useZodForm<
  Schema extends z.ZodType<Record<string, unknown>, Record<string, unknown>>,
>(schema: Schema, initial: z.input<Schema>) {
  type Input = z.input<Schema>
  type Output = z.output<Schema>

  const values = reactive(clone(initial)) as UnwrapRef<Input>
  const baseline = ref(JSON.stringify(initial))
  const touched = reactive<Record<string, boolean>>({})
  const submitAttempted = ref(false)
  const submitting = ref(false)
  const serverErrors = ref<Errors>({})

  const parsed = computed(() => schema.safeParse(values))

  const allErrors = computed<Errors>(() => {
    const result = parsed.value
    if (result.success) return {}
    const map: Errors = {}
    for (const issue of result.error.issues) {
      const key = issue.path.join('.')
      if (map[key] === undefined) map[key] = issue.message
    }
    return map
  })

  const errors = computed<Errors>(() => {
    const visible: Errors = {}
    for (const [key, message] of Object.entries(allErrors.value)) {
      const root = key.split('.')[0] ?? key
      if (submitAttempted.value || touched[key] || touched[root]) visible[key] = message
    }
    return { ...visible, ...serverErrors.value }
  })

  const isValid = computed(() => parsed.value.success)
  const isDirty = computed(() => JSON.stringify(values) !== baseline.value)

  // Editar borra los errores del servidor: ya no describen lo que hay en pantalla.
  watch(
    () => JSON.stringify(values),
    () => {
      if (Object.keys(serverErrors.value).length) serverErrors.value = {}
    },
  )

  function touch(field: string): void {
    touched[field] = true
  }

  /** Vuelve a un estado limpio: con `next`, ese pasa a ser el estado guardado. */
  function reset(next?: Input): void {
    const source = next ?? (JSON.parse(baseline.value) as Input)
    Object.assign(values as object, clone(source))
    baseline.value = JSON.stringify(source)
    for (const key of Object.keys(touched)) delete touched[key]
    submitAttempted.value = false
    serverErrors.value = {}
  }

  function setServerErrors(map: Errors): void {
    serverErrors.value = map
  }

  /**
   * Valida y, si todo está bien, llama a `action` con los datos ya transformados
   * por el esquema. Devuelve `true` si se ejecutó la acción sin errores.
   */
  async function handleSubmit(action: (data: Output) => Promise<void> | void): Promise<boolean> {
    submitAttempted.value = true
    const result = parsed.value
    if (!result.success || submitting.value) return false
    submitting.value = true
    try {
      await action(result.data as Output)
      return true
    } finally {
      submitting.value = false
    }
  }

  return {
    values,
    errors,
    isValid,
    isDirty,
    submitting,
    touch,
    reset,
    setServerErrors,
    handleSubmit,
  }
}
