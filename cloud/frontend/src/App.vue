<script setup lang="ts">
import { Toaster, useTheme } from '@savi/ui'
import { THEME_STORAGE_KEY } from '@/lib/theme'

// Aplica el tema (claro, oscuro o el del sistema) antes del primer render de cualquier vista.
useTheme({ storageKey: THEME_STORAGE_KEY })
</script>

<template>
  <RouterView />
  <Toaster />
</template>
