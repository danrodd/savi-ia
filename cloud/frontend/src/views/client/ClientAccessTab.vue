<script setup lang="ts">
import AccessPolicyCard from '@/components/AccessPolicyCard.vue'
import { useClientContext } from '@/lib/clientContext'

const { id, client, reload } = useClientContext()
</script>

<template>
  <AccessPolicyCard v-if="client" :client-id="id" :policy="client.access_policy" @saved="reload()" />
</template>
