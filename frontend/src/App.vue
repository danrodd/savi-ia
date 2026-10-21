<script setup lang="ts">
import { RouterView } from 'vue-router'
import Toaster from '@/components/ui/Toaster.vue'
import { useTheme } from '@/composables/useTheme'
import { useAuthStore } from '@/modules/auth/stores/authStore'
import { usePermisosPolling } from '@/modules/permisos'
import { UpdateNotice } from '@/modules/updates'

useTheme()
// Polling automático del hash de versión de módulos. Se monta una vez
// a nivel App; vive mientras la app esté abierta.
usePermisosPolling()
const auth = useAuthStore()
</script>

<template>
  <RouterView />
  <!-- `/updates/status` pide sesión: el aviso aparece después del ingreso. -->
  <UpdateNotice v-if="auth.isAuthenticated" />
  <Toaster />
</template>
