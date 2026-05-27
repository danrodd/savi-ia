<script setup lang="ts">
defineProps<{ text: string }>()
</script>

<template>
  <div class="user-message">
    <div class="bubble">{{ text }}</div>
  </div>
</template>

<style scoped>
.user-message {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--space-7);
  animation: fadeInUp 0.3s var(--ease-out);
}

.bubble {
  max-width: 75%;
  padding: var(--space-3) var(--space-5);
  background: var(--surface-subtle);
  border: 1px solid var(--border);
  border-radius: 16px 16px 4px 16px;
  color: var(--text);
  font-size: 14.5px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
}

@media (max-width: 767px) {
  .user-message {
    margin-bottom: var(--space-6);
  }
  .bubble {
    max-width: 88%;
    font-size: 14px;
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
