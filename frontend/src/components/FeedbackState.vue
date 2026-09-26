<template>
  <tr v-if="loading || error || empty">
    <td :colspan="colspan" class="feedback-cell">
      <div class="feedback-state" :class="{ 'is-error': error }">
        <template v-if="loading">
          <span class="feedback-icon" aria-hidden="true">⏳</span>
          <span class="feedback-text">{{ loadingText }}</span>
        </template>
        <template v-else-if="error">
          <span class="feedback-icon" aria-hidden="true">⚠️</span>
          <span class="feedback-text">{{ error }}</span>
          <button v-if="retryLabel" class="btn small" type="button" @click="emit('retry')">{{ retryLabel }}</button>
        </template>
        <template v-else>
          <span class="feedback-icon" aria-hidden="true">📋</span>
          <span class="feedback-text">{{ emptyText }}</span>
          <slot />
        </template>
      </div>
    </td>
  </tr>
</template>

<script setup lang="ts">
/** 列表空态/加载态/接口失败态的统一回执：失败时给一句原因和一个可重复点击的重试。 */
withDefaults(
  defineProps<{
    colspan: number
    loading?: boolean
    error?: string
    empty?: boolean
    emptyText?: string
    loadingText?: string
    retryLabel?: string
  }>(),
  {
    loading: false,
    error: '',
    empty: false,
    emptyText: '暂无数据',
    loadingText: '数据加载中…',
    retryLabel: '重新加载',
  },
)

const emit = defineEmits<{ retry: [] }>()
</script>
