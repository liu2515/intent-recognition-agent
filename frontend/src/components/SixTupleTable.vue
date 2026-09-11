<script setup>
import { computed } from 'vue'

const props = defineProps({ value: Object })

const labels = {
  subject: '① 主体', action: '② 动作', business_object: '③ 业务对象',
  context_parameters: '④ 上下文参数', constraints: '⑤ 约束', goal: '⑥ 目标',
}

const subjectLabel = computed(() => {
  const subject = props.value?.subject
  if (!subject) return ''
  return subject.username
    ? `${subject.username}（${subject.user_id || '未登记'}）`
    : subject.user_id || subject.role || ''
})
</script>

<template>
  <section class="panel tuple-panel">
    <div class="panel-head"><h3>业务意图六元组</h3><span>{{ subjectLabel ? `当前主体：${subjectLabel}` : 'BusinessRequest IR' }}</span></div>
    <div v-if="value" class="tuple-grid">
      <article v-for="(content, key) in value" :key="key">
        <h4>{{ labels[key] || key }}</h4>
        <pre>{{ JSON.stringify(content, null, 2) }}</pre>
      </article>
    </div>
    <p v-else class="empty">结构化结果会保留在原始请求信封中，不会替代用户原文。</p>
  </section>
</template>
