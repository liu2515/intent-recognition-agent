<script setup>
import { computed } from 'vue'

const props = defineProps({ trace: { type: Array, default: () => [] } })

const nodeInfo = {
  receive_request: ['接收用户请求', '读取原始文本、用户身份和当前会话信息。'],
  normalize_input: ['输入规范化', '清理输入格式，保留需要识别的业务表达和参数。'],
  retrieve_knowledge: ['检索知识图谱', '查找与当前动作、对象和参数相关的已生效知识。'],
  evaluate_knowledge: ['判断知识覆盖', '判断现有知识是完全命中、部分命中还是未命中。'],
  rule_translate: ['规则识别', '使用命中的规则，并用本次请求参数覆盖规则槽位。'],
  prepare_model_messages: ['准备模型消息', '组织用户原文、知识结果、缺失项和补充信息。'],
  llm_decide_next: ['LLM 决定下一步', '模型判断是否调用工具，或直接生成结构化六元组。'],
  readonly_tools: ['执行查询工具', '执行模型选择的只读业务查询工具，并返回查询结果。'],
  compile_six_tuple: ['生成结构化六元组', '生成主体、动作、业务对象、上下文参数、约束和目标。'],
  validate_tuple: ['六元组校验', '校验必填项、歧义、业务约束以及是否需要用户确认。'],
  clarify_with_user: ['用户补充', '暂停流程，等待用户补齐缺失或存在歧义的信息。'],
  confirm_with_user: ['用户确认', '等待用户确认需要授权或具有业务影响的请求。'],
  finalize_tuple: ['最终定稿', '固化完成校验和确认后的六元组识别结果。'],
  propose_knowledge_writeback: ['生成知识', '将确认后的识别结果写入可复用的活动知识。'],
  __end__: ['流程结束', '保存识别结果和执行轨迹，结束当前任务。'],
}

function titleOf(event) {
  return event.title || nodeInfo[event.node]?.[0] || event.node
}

function descriptionOf(event) {
  return event.summary || nodeInfo[event.node]?.[1] || '执行当前工作流节点。'
}

function formatToolCall(call) {
  const label = call.label || call.name || '未知工具'
  const technicalName = call.name && call.name !== label ? ` (${call.name})` : ''
  const callId = call.id ? ` · ${call.id}` : ''
  return `${label}${technicalName}${callId} · 参数 ${JSON.stringify(call.args || {})}`
}

function asDate(value) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatTimestamp(value) {
  const date = asDate(value)
  if (!date) return '--:--:--.---'
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    fractionalSecondDigits: 3,
    hour12: false,
  }).format(date)
}

function formatDuration(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '--'
  const milliseconds = Math.max(0, Number(value))
  if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`
  if (milliseconds < 60000) return `${(milliseconds / 1000).toFixed(2)} s`
  const minutes = Math.floor(milliseconds / 60000)
  const seconds = ((milliseconds % 60000) / 1000).toFixed(1)
  return `${minutes} min ${seconds} s`
}

function durationOf(event, index) {
  if (event.duration_ms !== null && event.duration_ms !== undefined) return event.duration_ms
  const completed = asDate(event.completed_at || event.created_at)
  const started = asDate(event.started_at || (index ? props.trace[index - 1]?.created_at : null))
  return started && completed ? completed.getTime() - started.getTime() : null
}

function elapsedOf(event, index) {
  if (event.elapsed_ms !== null && event.elapsed_ms !== undefined) return event.elapsed_ms
  const completed = asDate(event.completed_at || event.created_at)
  const started = asDate(props.trace[0]?.started_at || props.trace[0]?.created_at)
  return started && completed ? completed.getTime() - started.getTime() : durationOf(event, index)
}

const totalDuration = computed(() => {
  if (!props.trace.length) return null
  return elapsedOf(props.trace[props.trace.length - 1], props.trace.length - 1)
})
</script>

<template>
  <section class="panel trace-panel">
    <div class="panel-head">
      <h3>执行轨迹</h3>
      <span>
        {{ trace.length }} 个执行步骤
        <template v-if="totalDuration !== null"> · 累计 {{ formatDuration(totalDuration) }}</template>
      </span>
    </div>

    <div v-if="trace.length" class="trace-grid">
      <article
        v-for="(event, index) in trace"
        :key="`${event.sequence}-${event.node}-${event.task_id || ''}`"
        class="trace-card"
        :class="{ latest: index === props.trace.length - 1 }"
      >
        <header>
          <span class="step-code">T{{ event.sequence || index + 1 }}</span>
          <span v-if="event.task_id" class="task-code">{{ event.task_id }}</span>
        </header>
        <div class="timing-row">
          <time :datetime="event.completed_at || event.created_at">
            {{ formatTimestamp(event.completed_at || event.created_at) }}
          </time>
          <b>耗时 {{ formatDuration(durationOf(event, index)) }}</b>
        </div>
        <small class="time-range">
          <span>{{ formatTimestamp(event.started_at) }} → {{ formatTimestamp(event.completed_at || event.created_at) }}</span>
          <span>累计 {{ formatDuration(elapsedOf(event, index)) }}</span>
        </small>
        <strong>{{ titleOf(event) }}</strong>
        <p>{{ descriptionOf(event) }}</p>

        <small
          v-for="(call, callIndex) in event.tool_calls || []"
          :key="`${event.sequence}-call-${call.id || callIndex}`"
          class="detail"
        >
          <em>工具调用 #{{ callIndex + 1 }}</em>{{ formatToolCall(call) }}
        </small>
        <small
          v-if="event.node === 'llm_decide_next' && !event.tool_calls?.length"
          class="detail muted-detail"
        >
          <em>工具调用</em>本轮未调用工具，直接进入下一步
        </small>
        <small
          v-for="result in event.tool_results || []"
          :key="`${event.sequence}-${result.name}`"
          class="detail"
        >
          <em>工具结果</em>{{ result.label }}：{{ result.summary }}
        </small>
      </article>
    </div>

    <p v-else class="empty">识别开始后，将按 T1 到 Tn 显示实际执行步骤。</p>
  </section>
</template>

<style scoped>
.trace-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.trace-panel { margin-top: 14px; }

.trace-card {
  min-width: 0;
  padding: 12px;
  border: 1px solid #1d382c;
  border-radius: 10px;
  background: #07130e;
}

.trace-card.latest {
  border-color: #43c989;
  box-shadow: inset 0 0 0 1px rgba(78, 229, 154, 0.1);
}

.trace-card header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 9px;
}

.step-code {
  display: inline-grid;
  place-items: center;
  min-width: 34px;
  height: 24px;
  padding: 0 7px;
  border-radius: 6px;
  color: #06110c;
  background: #4ee59a;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.task-code {
  color: #708d7f;
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.timing-row,
.time-range {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-variant-numeric: tabular-nums;
}

.timing-row {
  margin-bottom: 4px;
  color: #8aa79a;
  font-size: 10px;
}

.timing-row b {
  color: #4ee59a;
  font-size: 10px;
  white-space: nowrap;
}

.time-range {
  margin-bottom: 9px;
  color: #506c5f;
  font-size: 9px;
}

.time-range span:first-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.time-range span:last-child {
  white-space: nowrap;
}

strong {
  display: block;
  color: #d8e9e0;
  font-size: 13px;
  font-weight: 700;
}

.trace-card p {
  min-height: 52px;
  margin: 6px 0 0;
  color: #789486;
  font-size: 11px;
  line-height: 1.55;
}

.detail {
  display: block;
  margin-top: 8px;
  padding-top: 7px;
  border-top: 1px dashed #1b3328;
  color: #8aa79a;
  font-size: 10px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.detail em {
  display: inline-block;
  margin-right: 5px;
  color: #4ee59a;
  font-style: normal;
}

.muted-detail { color: #607b6e; }

@media (max-width: 1300px) {
  .trace-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}

@media (max-width: 1000px) {
  .trace-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 720px) {
  .trace-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 480px) {
  .trace-grid { grid-template-columns: 1fr; }
}
</style>
