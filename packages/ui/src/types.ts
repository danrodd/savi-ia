/** Opción de `Select`. */
export interface SelectOption<V extends string | number = string> {
  value: V
  label: string
  disabled?: boolean
}

/** Regla de `PasswordField`: se muestra como requisito y se tilda cuando `test` da verdadero. */
export interface PasswordRule {
  label: string
  test: (value: string) => boolean
}

/** Tono de color de `Badge`, `Alert` y `KpiCard`. */
export type Tone = 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'brand'

/** Columna de `DataTable`. Cada celda se puede reemplazar con el slot `cell-<key>`. */
export interface TableColumn {
  key: string
  label: string
  align?: 'left' | 'right' | 'center'
  /** Ancho CSS (`'120px'`, `'20%'`). */
  width?: string
  mono?: boolean
}

/** Pestaña de `Tabs`. Con `to` es un enlace del router; sin él, una pestaña local. */
export interface TabItem {
  key: string
  label: string
  to?: string | Record<string, unknown>
  count?: number
}

/** Paso de `Stepper`. */
export interface StepItem {
  key: string
  label: string
}
