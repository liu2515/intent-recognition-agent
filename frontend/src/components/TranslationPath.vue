<script setup>
import { computed } from 'vue'

const props = defineProps({ result: Object })

const modeLabel = { rule: '规则匹配识别', hybrid: '知识辅助识别', llm: '模型推理识别' }
const statusLabel = {
  processing: '处理中', needs_clarification: '等待补充', requires_confirmation: '等待确认',
  completed: '已完成', invalid: '无效', cancelled: '已取消',
}
const effectiveStatus = computed(() => (
  props.result?.validation_errors?.length ? 'invalid' : props.result?.status
))
</script>

<template>
  <section v-if="result" class="path-card">
    <span class="eyebrow">RECOGNITION PATH</span>
    <div class="path-row">
      <div><small>识别状态</small><strong :class="`status-${effectiveStatus}`">{{ statusLabel[effectiveStatus] || effectiveStatus }}</strong></div>
      <span>→</span>
      <div><small>知识覆盖</small><strong>{{ result.knowledge_coverage || '—' }}</strong></div>
      <span>→</span>
      <div><small>识别方式</small><strong>{{ modeLabel[result.translation_mode] || '—' }}</strong></div>
      <span>→</span>
      <div><small>版本</small><strong>rev.{{ result.revision }}</strong></div>
    </div>
  </section>
</template>
