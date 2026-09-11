<script setup>
import { computed, reactive, ref } from 'vue'

const props = defineProps({
  rules: { type: Array, default: () => [] },
  candidates: { type: Array, default: () => [] },
  busy: Boolean,
})
const emit = defineEmits(['approve', 'reject', 'refresh'])
const reviewer = ref('admin')
const reasons = reactive({})
const pendingCount = computed(() => props.candidates.filter(item => item.status === 'pending').length)

function approve(item) {
  emit('approve', { templateId: item.template_id, reviewer: reviewer.value.trim() || 'admin' })
}

function reject(item) {
  const reason = (reasons[item.template_id] || '').trim()
  if (!reason) return
  emit('reject', {
    templateId: item.template_id,
    reviewer: reviewer.value.trim() || 'admin',
    reason,
  })
}
</script>

<template>
  <section class="panel knowledge-admin">
    <div class="panel-head">
      <div><span class="eyebrow">KNOWLEDGE REVIEW</span><h3>知识审核中心</h3></div>
      <button class="ghost-button" :disabled="busy" @click="emit('refresh')">刷新</button>
    </div>

    <div class="knowledge-summary">
      <article><strong>{{ pendingCount }}</strong><span>待审核</span></article>
      <article><strong>{{ rules.length }}</strong><span>已生效</span></article>
      <label>审核人<input v-model="reviewer" placeholder="admin" /></label>
    </div>

    <div v-if="candidates.length" class="candidate-list">
      <article v-for="item in candidates" :key="item.template_id" class="candidate-card">
        <div class="candidate-title">
          <strong>{{ item.canonical_utterance }}</strong>
          <span :class="`badge-${item.status}`">{{ item.status }}</span>
        </div>
        <dl>
          <dt>动作</dt><dd>{{ item.six_tuple?.action?.name || '-' }}</dd>
          <dt>对象</dt><dd>{{ item.six_tuple?.business_object?.name || item.six_tuple?.business_object?.type || '-' }}</dd>
          <dt>来源</dt><dd>{{ item.origin }} · {{ item.created_by }}</dd>
        </dl>
        <template v-if="item.status === 'pending'">
          <input v-model="reasons[item.template_id]" class="reason-input" placeholder="拒绝时填写原因" />
          <div class="candidate-actions">
            <button class="reject-button" :disabled="busy || !reasons[item.template_id]?.trim()" @click="reject(item)">拒绝</button>
            <button :disabled="busy" @click="approve(item)">批准并生效</button>
          </div>
        </template>
        <p v-else-if="item.rejection_reason" class="rejection-reason">原因：{{ item.rejection_reason }}</p>
      </article>
    </div>
    <p v-else class="empty">模型生成的新知识会先进入这里，审核通过后才参与规则匹配。</p>
  </section>
</template>

<style scoped>
.knowledge-admin { min-height: 420px; }
.panel-head > div h3 { margin: 3px 0 0; }
.ghost-button { color: #84d8ad; background: transparent; border-color: #315a47; }
.knowledge-summary { display: grid; grid-template-columns: 92px 92px minmax(150px, 1fr); gap: 10px; margin: 14px 0; }
.knowledge-summary article, .knowledge-summary label { padding: 10px; border: 1px solid #1e392c; border-radius: 10px; background: #08120e; }
.knowledge-summary strong { display: block; color: #62e3a4; font-size: 21px; }
.knowledge-summary span, .knowledge-summary label { color: #708c7d; font-size: 11px; }
.knowledge-summary input { width: 100%; margin-top: 6px; padding: 7px 9px; }
.candidate-list { display: grid; gap: 10px; max-height: 520px; overflow-y: auto; }
.candidate-card { padding: 13px; border: 1px solid #20392e; border-radius: 11px; background: #08120e; }
.candidate-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.candidate-title strong { color: #dcece4; font-size: 13px; line-height: 1.5; }
.candidate-title span { flex: none; padding: 3px 7px; border-radius: 20px; font-size: 9px; text-transform: uppercase; }
.badge-pending { color: #ffd36a; background: #4b3a13; }
.badge-rejected { color: #ff9a9a; background: #401c1c; }
.candidate-card dl { display: grid; grid-template-columns: 42px 1fr; gap: 5px; margin: 10px 0; font-size: 11px; }
.candidate-card dt { color: #567266; }
.candidate-card dd { margin: 0; color: #a9c1b5; }
.reason-input { width: 100%; padding: 8px 10px; }
.candidate-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 9px; }
.candidate-actions button { padding: 7px 11px; font-size: 11px; }
.reject-button { color: #ffaaaa; background: transparent; border-color: #713838; }
.rejection-reason { margin: 8px 0 0; color: #c48c8c; font-size: 11px; }
@media (max-width: 620px) { .knowledge-summary { grid-template-columns: 1fr 1fr; } .knowledge-summary label { grid-column: 1 / -1; } }
</style>
