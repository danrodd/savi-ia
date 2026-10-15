<script setup lang="ts">
import SubscriptionCard from '@/components/SubscriptionCard.vue'
import { useClientContext } from '@/lib/clientContext'

const { id } = useClientContext()
</script>

<template>
  <SubscriptionCard :key="id" :client-id="id" />
</template>
