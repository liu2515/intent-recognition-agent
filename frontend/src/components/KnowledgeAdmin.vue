<script setup>
defineProps({
  rules: { type: Array, default: () => [] },
  busy: Boolean,
})
const emit = defineEmits(['remove', 'refresh'])

function remove(item) {
  emit('remove', { templateId: item.template_id })
}
</script>

<template>
  <section class="panel knowledge-admin">
    <div class="panel-head">
      <div><span class="eyebrow">KNOWLEDGE BASE</span><h3>已生效知识</h3></div>
      <button class="ghost-button" :disabled="busy" @click="emit('refresh')">刷新</button>
    </div>

    <div class="knowledge-summary">
      <article><strong>{{ rules.length }}</strong><span>已生效</span></article>
      <p>用户确认后的模型识别结果会直接写入知识库并同步 Neo4j。</p>
    </div>

    <div v-if="rules.length" class="rule-list">
      <article v-for="item in rules" :key="item.template_id" class="rule-card">
        <div class="rule-title">
          <strong>{{ item.canonical_utterance }}</strong>
          <span>ACTIVE</span>
        </div>
        <dl>
          <dt>动作</dt><dd>{{ item.six_tuple?.action?.name || '-' }}</dd>
          <dt>对象</dt><dd>{{ item.six_tuple?.business_object?.name || item.six_tuple?.business_object?.type || '-' }}</dd>
          <dt>来源用户</dt><dd>{{ item.reviewed_by || item.created_by }}</dd>
        </dl>
        <div class="rule-actions">
          <button class="delete-button" :disabled="busy" @click="remove(item)">删除并同步图谱</button>
        </div>
      </article>
    </div>
    <p v-else class="empty">暂无已生效知识。</p>
  </section>
</template>

<style scoped>
.knowledge-admin { min-height: 420px; }
.panel-head > div h3 { margin: 3px 0 0; }
.ghost-button { color: #84d8ad; background: transparent; border-color: #315a47; }
.knowledge-summary { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 10px; margin: 14px 0; align-items: stretch; }
.knowledge-summary article, .knowledge-summary p { margin: 0; padding: 10px; border: 1px solid #1e392c; border-radius: 10px; background: #08120e; }
.knowledge-summary strong { display: block; color: #62e3a4; font-size: 21px; }
.knowledge-summary span, .knowledge-summary p { color: #708c7d; font-size: 11px; line-height: 1.6; }
.rule-list { display: grid; gap: 10px; max-height: 520px; overflow-y: auto; }
.rule-card { padding: 13px; border: 1px solid #20392e; border-radius: 11px; background: #08120e; }
.rule-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.rule-title strong { color: #dcece4; font-size: 13px; line-height: 1.5; }
.rule-title span { flex: none; padding: 3px 7px; border-radius: 20px; color: #69e7aa; background: #123b29; font-size: 9px; }
.rule-card dl { display: grid; grid-template-columns: 48px 1fr; gap: 5px; margin: 10px 0; font-size: 11px; }
.rule-card dt { color: #567266; }
.rule-card dd { margin: 0; color: #a9c1b5; }
.rule-actions { display: flex; justify-content: flex-end; margin-top: 9px; }
.delete-button { padding: 7px 11px; color: #ff8f8f; background: #2b1010; border-color: #713838; font-size: 11px; }
@media (max-width: 620px) { .knowledge-summary { grid-template-columns: 1fr; } }
</style>
