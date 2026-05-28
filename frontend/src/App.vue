<script setup lang="ts">
import { RouterView } from 'vue-router'
import Toaster from '@/components/ui/Toaster.vue'
import { useTheme } from '@/composables/useTheme'

useTheme()
</script>

<template>
  <RouterView />
  <Toaster />
</template>
