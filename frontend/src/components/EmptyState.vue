<template>
  <div class="empty-box" role="status">
    <p class="empty-title">{{ title }}</p>
    <p v-if="description" class="empty-desc">{{ description }}</p>
    <button v-if="retryable" class="btn" type="button" @click="$emit('retry')">重试</button>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string
    description?: string
    retryable?: boolean
  }>(),
  {
    title: '数据暂时不可用',
    description: '',
    retryable: true,
  },
)

defineEmits<{ (event: 'retry'): void }>()
</script>

<style scoped>
.empty-box {
  padding: 24px 12px;
  text-align: center;
  color: var(--muted);
}
.empty-title {
  margin: 0 0 4px;
  font-size: 14px;
  color: #1f2937;
}
.empty-desc {
  margin: 0 0 12px;
  font-size: 12px;
}
</style>
