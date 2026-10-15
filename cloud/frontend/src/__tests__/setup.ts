import { config } from '@vue/test-utils'

// Los diálogos de @savi/ui (reka-ui) se montan en un portal fuera del componente. En los
// tests se renderizan en el lugar para poder consultarlos desde el wrapper.
config.global.stubs = {
  ...config.global.stubs,
  DialogPortal: { template: '<div><slot /></div>' },
}
