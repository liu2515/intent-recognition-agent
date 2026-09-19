<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({ value: Object, tasks: { type: Array, default: () => [] } })
const activeTaskId = ref('')

watch(() => props.tasks, tasks => {
  if (tasks.length && !tasks.some(task => task.task_id === activeTaskId.value)) {
    activeTaskId.value = tasks[0].task_id
  }
}, { immediate: true })

const activeTask = computed(() => props.tasks.find(task => task.task_id === activeTaskId.value))
const displayedValue = computed(() => activeTask.value?.six_tuple || props.value)

const statusLabels = {
  pending: '等待中', processing: '处理中', needs_clarification: '待补充',
  requires_confirmation: '待确认', completed: '已完成', invalid: '无效', cancelled: '已取消',
}

const labels = {
  subject: '① 主体', action: '② 动作', business_object: '③ 业务对象',
  context_parameters: '④ 上下文参数', constraints: '⑤ 约束', goal: '⑥ 目标',
}

const subjectLabel = computed(() => {
  const subject = displayedValue.value?.subject
  if (!subject) return ''
  return subject.username
    ? `${subject.username}（${subject.user_id || '未登记'}）`
    : subject.user_id || subject.role || ''
})
</script>

<template>
  <section class="panel tuple-panel">
    <div v-if="tasks.length" class="task-tabs" role="tablist" aria-label="意图任务">
      <button
        v-for="task in tasks"
        :key="task.task_id"
        type="button"
        class="task-tab"
        :class="{ active: task.task_id === activeTaskId }"
        role="tab"
        :aria-selected="task.task_id === activeTaskId"
        @click="activeTaskId = task.task_id"
      >
        任务 {{ task.sequence }}：{{ task.action_hint || task.text }}
        <small>{{ statusLabels[task.status] || task.status }}</small>
      </button>
    </div>
    <div class="panel-head"><h3>业务意图六元组</h3><span>{{ subjectLabel ? `当前主体：${subjectLabel}` : 'BusinessRequest IR' }}</span></div>
    <div v-if="displayedValue" class="tuple-grid">
      <article v-for="(content, key) in displayedValue" :key="key">
        <h4>{{ labels[key] || key }}</h4>
        <pre>{{ JSON.stringify(content, null, 2) }}</pre>
      </article>
    </div>
    <p v-else class="empty">结构化结果会保留在原始请求信封中，不会替代用户原文。</p>
  </section>
</template>

<style scoped>
.task-tabs { display: flex; gap: 8px; margin: 14px 0; overflow-x: auto; padding-bottom: 2px; }
.task-tab { flex: 0 0 auto; padding: 8px 11px; border: 1px solid #29483a; border-radius: 9px; color: #9eb8aa; background: #07110d; font-size: 12px; font-weight: 600; text-align: left; }
.task-tab.active { border-color: #4ee59a; color: #effff7; background: #123022; box-shadow: 0 0 0 2px #4ee59a18; }
.task-tab small { display: block; margin-top: 3px; color: #ffd36a; font-size: 10px; font-weight: 500; }
.task-tab.active small { color: #70eeb1; }
</style>
