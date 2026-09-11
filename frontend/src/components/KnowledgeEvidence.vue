<script setup>
defineProps({ evidence: { type: Array, default: () => [] }, hypotheses: { type: Array, default: () => [] } })
</script>

<template>
  <section class="panel">
    <div class="panel-head"><h3>语义证据</h3><span>{{ evidence.length }} 项</span></div>
    <div v-if="evidence.length" class="evidence-list">
      <article v-for="(item, index) in evidence" :key="`${item.field_path}-${index}`">
        <code>{{ item.field_path }}</code>
        <p>{{ item.source_text || item.knowledge_id || item.source }}</p>
        <span>{{ Math.round(item.confidence * 100) }}%</span>
      </article>
    </div>
    <p v-else class="empty">运行后显示字段对应的原文或知识来源。</p>
    <template v-if="hypotheses.length">
      <h4>候选意图</h4>
      <div class="hypotheses">
        <span v-for="item in hypotheses" :key="item.action">{{ item.action }} · {{ Math.round(item.confidence * 100) }}%</span>
      </div>
    </template>
  </section>
</template>
