<script setup>
import { computed } from 'vue'

const props = defineProps({ graph: Object, busy: Boolean, runtimeSubject: Object })
const emit = defineEmits(['refresh', 'sync'])

const kindOrder = ['intent_instance', 'subject', 'action', 'object', 'parameter', 'constraint', 'goal']
const kindLabels = { intent_instance: '运行实例', subject: '模板主体', subject_instance: '业务主体', action: '业务动作', object: '业务对象', parameter: '上下文参数', constraint: '业务约束', goal: '目标状态' }
const columnWidth = 235
const rowHeight = 92

const layout = computed(() => {
  const nodes = props.graph?.nodes || []
  const groups = Object.fromEntries(kindOrder.map(kind => [kind, []]))
  nodes.forEach(node => {
    const columnKind = node.kind === 'subject_instance' ? 'subject' : node.kind
    ;(groups[columnKind] || (groups[columnKind] = [])).push(node)
  })
  const positions = {}
  const placed = []
  kindOrder.forEach((kind, column) => {
    ;(groups[kind] || []).forEach((node, row) => {
      const value = { ...node, x: 22 + column * columnWidth, y: 48 + row * rowHeight }
      positions[node.id] = value
      placed.push(value)
    })
  })
  const maxRows = Math.max(1, ...kindOrder.map(kind => (groups[kind] || []).length))
  return {
    nodes: placed,
    positions,
    width: 25 + kindOrder.length * columnWidth,
    height: 70 + maxRows * rowHeight,
  }
})

const edges = computed(() => (props.graph?.edges || []).map(edge => {
  const source = layout.value.positions[edge.source]
  const target = layout.value.positions[edge.target]
  if (!source || !target) return null
  const startX = source.x + 175
  const startY = source.y + 24
  const endX = target.x
  const endY = target.y + 24
  const middle = (startX + endX) / 2
  return { ...edge, path: `M ${startX} ${startY} C ${middle} ${startY}, ${middle} ${endY}, ${endX} ${endY}` }
}).filter(Boolean))

function shortLabel(value) {
  return value.length > 20 ? `${value.slice(0, 19)}…` : value
}
</script>

<template>
  <section class="panel knowledge-graph-panel">
    <div class="panel-head graph-head">
      <div><span class="eyebrow">KNOWLEDGE GRAPH</span><h3>移动业务知识图谱</h3></div>
      <div class="graph-actions">
        <span>{{ graph?.source || 'mongodb-projection' }}</span>
        <button class="ghost-button" :disabled="busy" @click="emit('sync')">同步 Neo4j</button>
        <button class="ghost-button" :disabled="busy" @click="emit('refresh')">刷新</button>
      </div>
    </div>

    <div class="graph-stat-row">
      <span v-if="runtimeSubject?.username" class="runtime-subject">本次运行主体：{{ runtimeSubject.username }}（{{ runtimeSubject.user_id }}）</span>
      <span>模板 {{ graph?.summary?.template_count || 0 }}</span>
      <span>节点 {{ graph?.summary?.node_count || 0 }}</span>
      <span>关系 {{ graph?.summary?.edge_count || 0 }}</span>
      <span>实名主体 {{ graph?.summary?.runtime_subject_count || 0 }}</span>
      <span :class="graph?.neo4j?.connected ? 'connected' : 'disconnected'">
        Neo4j {{ graph?.neo4j?.connected ? '已连接' : '未连接' }}
      </span>
    </div>
    <p v-if="runtimeSubject?.username" class="runtime-note">“本人”是可复用的模板主体；任务完成后，{{ runtimeSubject.username }} 会作为业务主体实例写入图谱并关联到“本人”。</p>
    <p v-if="graph?.neo4j?.error" class="graph-warning">{{ graph.neo4j.error }}</p>

    <div v-if="layout.nodes.length" class="knowledge-canvas">
      <svg :viewBox="`0 0 ${layout.width} ${layout.height}`" role="img" aria-label="知识关系图">
        <defs>
          <marker id="knowledge-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 Z" fill="#396b55" />
          </marker>
        </defs>
        <g class="edges">
          <path v-for="edge in edges" :key="edge.id" :d="edge.path" marker-end="url(#knowledge-arrow)" :class="{ pending: edge.status === 'pending' }" />
        </g>
        <g v-for="node in layout.nodes" :key="node.id" :transform="`translate(${node.x}, ${node.y})`" :class="['knowledge-node', `node-${node.kind}`]">
          <rect width="175" height="48" rx="9" />
          <text x="12" y="18" class="kind-text">{{ kindLabels[node.kind] || node.kind }}</text>
          <text x="12" y="36" class="label-text"><title>{{ node.label }}</title>{{ shortLabel(node.label) }}</text>
        </g>
      </svg>
    </div>
    <p v-else class="empty">批准知识候选后，这里会展示动作、对象、参数、约束和目标之间的关系。</p>
  </section>
</template>

<style scoped>
.knowledge-graph-panel { min-height: 420px; }
.graph-head > div:first-child h3 { margin: 3px 0 0; }
.graph-actions { display: flex; align-items: center; gap: 8px; }
.graph-actions > span { color: #698678; font-size: 10px; }
.ghost-button { padding: 7px 10px; color: #84d8ad; background: transparent; border-color: #315a47; font-size: 10px; }
.graph-stat-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 8px; }
.graph-stat-row span { padding: 5px 9px; border-radius: 20px; color: #7f9d8f; background: #0a1711; font-size: 10px; }
.graph-stat-row .connected { color: #58e69d; }
.graph-stat-row .disconnected { color: #d7a653; }
.graph-stat-row .runtime-subject { color: #7deab5; border: 1px solid #2f7354; }
.runtime-note { margin: 8px 0; color: #779486; font-size: 11px; }
.graph-warning { margin: 8px 0; color: #d7a653; font-size: 11px; }
.knowledge-canvas { width: 100%; overflow: auto; border: 1px solid #182f24; border-radius: 11px; background: linear-gradient(#0a1611dd, #07100d); }
.knowledge-canvas svg { display: block; min-width: 100%; min-height: 300px; }
.edges path { fill: none; stroke: #396b55; stroke-width: 1.5; opacity: .78; }
.edges path.pending { stroke: #8a713b; stroke-dasharray: 5 4; }
.knowledge-node rect { fill: #0d2018; stroke: #2f624c; stroke-width: 1.2; }
.knowledge-node.node-action rect { fill: #123b2a; stroke: #55d797; }
.knowledge-node.node-subject rect { stroke: #d4d5dc; }
.knowledge-node.node-subject_instance rect { fill: #12353a; stroke: #58dbe8; stroke-width: 2; }
.knowledge-node.node-intent_instance rect { fill: #172d3a; stroke: #68b7e8; stroke-width: 2; }
.knowledge-node.node-object rect { stroke: #55a9d7; }
.knowledge-node.node-parameter rect { stroke: #9172da; }
.knowledge-node.node-constraint rect { stroke: #d3a64f; }
.knowledge-node.node-goal rect { stroke: #4fd3c5; }
.kind-text { fill: #668b79; font: 8px Inter, sans-serif; text-transform: uppercase; }
.label-text { fill: #d3e7dc; font: 11px "Microsoft YaHei", sans-serif; }
</style>
