<script setup lang="ts">
import { Toaster, useTheme } from '@savi/ui'
import { RouterView } from 'vue-router'
import { STORAGE_KEYS } from '@/lib/storageKeys'
import { useAuthStore } from '@/modules/auth/stores/authStore'
import { usePermisosPolling } from '@/modules/permisos'
import { UpdateNotice } from '@/modules/updates'

useTheme({ storageKey: STORAGE_KEYS.THEME_MODE })
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
