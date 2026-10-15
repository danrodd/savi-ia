<script setup lang="ts">
import { Toaster, useTheme } from '@savi/ui'
import { RouterView } from 'vue-router'
import { STORAGE_KEYS } from '@/lib/storageKeys'
import { usePermisosPolling } from '@/modules/permisos'

useTheme({ storageKey: STORAGE_KEYS.THEME_MODE })
// Polling automático del hash de versión de módulos. Se monta una vez
// a nivel App; vive mientras la app esté abierta.
usePermisosPolling()
</script>

<template>
  <RouterView />
  <Toaster />
</template>
