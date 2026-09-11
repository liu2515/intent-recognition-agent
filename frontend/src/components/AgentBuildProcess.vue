<script setup>
defineProps({ trace: { type: Array, default: () => [] } })
</script>

<template>
  <section class="panel">
    <div class="panel-head"><h3>执行轨迹</h3><span>{{ trace.length }} 个执行步骤</span></div>
    <ol v-if="trace.length" class="trace-list">
      <li v-for="event in trace" :key="`${event.sequence}-${event.node}`">
        <b>{{ event.sequence }}</b><span>{{ event.node }}</span>
      </li>
    </ol>
    <p v-else class="empty">LangGraph 运行后显示实际执行步骤。</p>
  </section>
</template>
