<script setup lang="ts">
import { watch } from 'vue'
import ClientTokensPanel from '@/components/ClientTokensPanel.vue'
import { consoleApi } from '@/lib/api'
import { useClientContext } from '@/lib/clientContext'
import { useAsync } from '@/lib/useAsync'

const { id } = useClientContext()
const tokens = useAsync(() => consoleApi.tokens(id.value))
watch(id, () => tokens.reload())
</script>

<template>
  <ClientTokensPanel
    :client-id="id"
    :tokens="tokens.data.value ?? []"
    :loading="tokens.loading.value"
    @changed="tokens.reload()"
  />
</template>
