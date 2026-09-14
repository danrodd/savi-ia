import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AppVersion from '../AppVersion.vue'

describe('AppVersion', () => {
  it('muestra la versión incrustada en el build', () => {
    const wrapper = mount(AppVersion)

    expect(wrapper.text()).toBe(`SAVI ${__APP_VERSION__}`)
  })

  it('nunca queda vacía: sin tag muestra el commit, sin git 0.0.0-dev', () => {
    expect(__APP_VERSION__).toMatch(
      /^(v\d+\.\d+\.\d+(-\d+-g[0-9a-f]+)?|[0-9a-f]{7,}|0\.0\.0-dev)(-sucio)?$/,
    )
  })
})
