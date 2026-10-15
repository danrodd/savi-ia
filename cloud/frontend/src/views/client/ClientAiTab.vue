<script setup lang="ts">
import AiPolicyCard from '@/components/AiPolicyCard.vue'
import { useClientContext } from '@/lib/clientContext'

const { id, client, reload } = useClientContext()
</script>

<template>
  <AiPolicyCard v-if="client" :client-id="id" :policy="client.ai_policy" @saved="reload()" />
</template>
