<script setup lang="ts">
import { RouterView } from 'vue-router'
import Toaster from '@/components/ui/Toaster.vue'
import { useTheme } from '@/composables/useTheme'
import { usePermisosPolling } from '@/modules/permisos'

useTheme()
// Polling automático del hash de versión de módulos. Se monta una vez
// a nivel App; vive mientras la app esté abierta.
usePermisosPolling()
</script>

<template>
  <RouterView />
  <Toaster />
</template>
