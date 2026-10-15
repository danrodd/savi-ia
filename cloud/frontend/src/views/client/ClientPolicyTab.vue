<script setup lang="ts">
import ClientPolicyCard from '@/components/ClientPolicyCard.vue'
import { useClientContext } from '@/lib/clientContext'

const { id, client, reload } = useClientContext()
</script>

<template>
  <ClientPolicyCard v-if="client" :client-id="id" :client="client" @saved="reload()" />
</template>
