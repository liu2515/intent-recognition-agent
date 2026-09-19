<script setup>
import { computed } from 'vue'

const props = defineProps({ graph: Object, trace: { type: Array, default: () => [] } })
const visited = computed(() => new Set(props.trace.map(item => item.node)))
const selectedTools = computed(() => {
  const labels = []
  for (const event of props.trace) {
    for (const tool of event.tool_calls || []) {
      if (tool.label && !labels.includes(tool.label)) labels.push(tool.label)
    }
  }
  return labels.slice(0, 2)
})
const executedStepCount = computed(() => props.trace.filter(item => item.node).length)

const positions = {
  receive_request: [30, 35],
  normalize_input: [220, 35],
  retrieve_knowledge: [410, 35],
  evaluate_knowledge: [600, 35],
  rule_translate: [820, 35],
  validate_tuple: [1030, 150],
  prepare_model_messages: [590, 235],
  llm_decide_next: [590, 385],
  readonly_tools: [285, 535],
  compile_six_tuple: [800, 535],
  clarify_with_user: [805, 260],
  confirm_with_user: [1055, 330],
  finalize_tuple: [1205, 500],
  propose_knowledge_writeback: [1205, 635],
  __end__: [975, 735],
}

const nodeWidth = 168
const nodeHeight = 64
const layoutNodes = computed(() => (props.graph?.nodes || []).map((node, index) => {
  const fallback = [30 + (index % 6) * 190, 35 + Math.floor(index / 6) * 130]
  const [x, y] = positions[node.id] || fallback
  return { ...node, x, y }
}))
const nodeMap = computed(() => Object.fromEntries(layoutNodes.value.map(node => [node.id, node])))

const traversed = computed(() => {
  const result = new Set()
  const path = props.trace.map(item => item.node).filter(Boolean)
  for (let index = 0; index < path.length - 1; index += 1) {
    result.add(`${path[index]}->${path[index + 1]}`)
  }
  return result
})

function edgePath(edge) {
  const source = nodeMap.value[edge.source]
  const target = nodeMap.value[edge.target]
  if (!source || !target) return ''

  const key = `${edge.source}->${edge.target}`
  const centerX = node => node.x + nodeWidth / 2
  const centerY = node => node.y + nodeHeight / 2
  const right = node => [node.x + nodeWidth, centerY(node)]
  const left = node => [node.x, centerY(node)]
  const top = node => [centerX(node), node.y]
  const bottom = node => [centerX(node), node.y + nodeHeight]

  const routes = {
    'evaluate_knowledge->prepare_model_messages': [bottom(source), [684, 190], [centerX(target), 190], top(target)],
    'rule_translate->validate_tuple': [bottom(source), [1005, 99], [1005, 118], [centerX(target), 118], top(target)],
    'llm_decide_next->readonly_tools': [left(source), [520, centerY(source)], [520, centerY(target)], right(target)],
    // The return path uses a dedicated lower channel so it never crosses the tool-call path.
    'readonly_tools->llm_decide_next': [left(source), [245, centerY(source)], [245, 685], [540, 685], [540, centerY(target)], left(target)],
    'llm_decide_next->compile_six_tuple': [right(source), [775, centerY(source)], [775, centerY(target)], left(target)],
    'compile_six_tuple->validate_tuple': [top(source), [centerX(source), 430], [985, 430], [985, 118], [centerX(target), 118], top(target)],
    'validate_tuple->clarify_with_user': [left(source), [975, centerY(source)], [975, centerY(target)], right(target)],
    'clarify_with_user->prepare_model_messages': [left(source), [780, centerY(source)], [780, centerY(target)], right(target)],
    'validate_tuple->confirm_with_user': [right(source), [1260, centerY(source)], [1260, 300], [centerX(target), 300], top(target)],
    // The successful validation path uses the upper-right channel.
    'validate_tuple->finalize_tuple': [right(source), [1340, centerY(source)], [1340, 260], [centerX(target), 260], top(target)],
    'validate_tuple->__end__': [bottom(source), [1114, 230], [1000, 230], [1000, 700], [centerX(target), 700], top(target)],
    // Confirmation uses a lower channel and therefore does not overlap the validation path.
    'confirm_with_user->finalize_tuple': [right(source), [1260, centerY(source)], [1260, 465], [centerX(target), 465], top(target)],
    'confirm_with_user->__end__': [left(source), [1015, centerY(source)], [1015, 700], [centerX(target), 700], top(target)],
    'finalize_tuple->propose_knowledge_writeback': [bottom(source), top(target)],
    'propose_knowledge_writeback->__end__': [bottom(source), [centerX(source), 715], [centerX(target), 715], top(target)],
  }

  const points = routes[key] || defaultRoute(source, target, { right, left, top, bottom, centerX, centerY })
  return roundedOrthogonalPath(points)
}

function defaultRoute(source, target, ports) {
  const { right, left, top, bottom, centerX, centerY } = ports
  if (target.x >= source.x + nodeWidth) return [right(source), left(target)]
  if (target.x + nodeWidth <= source.x) return [left(source), right(target)]
  if (target.y >= source.y + nodeHeight) return [bottom(source), top(target)]
  return [top(source), bottom(target)]
}

function roundedOrthogonalPath(points, radius = 9) {
  if (points.length < 2) return ''
  let path = `M ${points[0][0]} ${points[0][1]}`
  for (let index = 1; index < points.length - 1; index += 1) {
    const previous = points[index - 1]
    const current = points[index]
    const next = points[index + 1]
    const before = moveToward(current, previous, radius)
    const after = moveToward(current, next, radius)
    path += ` L ${before[0]} ${before[1]} Q ${current[0]} ${current[1]} ${after[0]} ${after[1]}`
  }
  const last = points[points.length - 1]
  path += ` L ${last[0]} ${last[1]}`
  return path
}

function moveToward(from, to, distance) {
  const dx = to[0] - from[0]
  const dy = to[1] - from[1]
  const length = Math.sqrt(dx * dx + dy * dy) || 1
  const amount = Math.min(distance, length / 2)
  return [from[0] + (dx / length) * amount, from[1] + (dy / length) * amount]
}

function labelPosition(edge) {
  const source = nodeMap.value[edge.source]
  const target = nodeMap.value[edge.target]
  if (!source || !target) return { x: 0, y: 0 }
  const labelPositions = {
    'evaluate_knowledge->rule_translate': [748, 28],
    'evaluate_knowledge->prepare_model_messages': [704, 178],
    'llm_decide_next->readonly_tools': [526, 370],
    'readonly_tools->llm_decide_next': [360, 676],
    'llm_decide_next->compile_six_tuple': [790, 465],
    'compile_six_tuple->validate_tuple': [969, 394],
    'validate_tuple->clarify_with_user': [967, 242],
    'clarify_with_user->prepare_model_messages': [785, 246],
    'validate_tuple->confirm_with_user': [1268, 279],
    'validate_tuple->finalize_tuple': [1340, 242],
    'validate_tuple->__end__': [1155, 690],
    'confirm_with_user->finalize_tuple': [1260, 449],
    'confirm_with_user->__end__': [1000, 690],
    'propose_knowledge_writeback->__end__': [1170, 721],
  }
  const fixed = labelPositions[`${edge.source}->${edge.target}`]
  if (fixed) return { x: fixed[0], y: fixed[1] }
  return {
    x: (source.x + target.x) / 2 + nodeWidth / 2,
    y: (source.y + target.y) / 2 + nodeHeight / 2 - 8,
  }
}

function isEdgeVisited(edge) {
  return traversed.value.has(`${edge.source}->${edge.target}`)
}
</script>

<template>
  <section class="panel graph-panel">
    <div class="panel-head">
      <div><h3>LangGraph 意图识别编排图</h3><small>实线高亮表示本次实际执行路径</small></div>
      <span>静态拓扑 {{ graph?.nodes?.length || 0 }} 节点 · {{ graph?.edges?.length || 0 }} 条边<span v-if="executedStepCount"> · 本次执行 {{ executedStepCount }} 步</span></span>
    </div>
    <div v-if="graph?.nodes" class="graph-scroll">
      <svg class="intent-graph" viewBox="0 0 1410 835" role="img" aria-label="意图识别 LangGraph 流程图">
        <defs>
          <marker id="arrow-idle" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="userSpaceOnUse">
            <path d="M0,0 L8,4 L0,8 Z" fill="#385247" />
          </marker>
          <marker id="arrow-active" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="userSpaceOnUse">
            <path d="M0,0 L8,4 L0,8 Z" fill="#55e7a1" />
          </marker>
          <filter id="active-glow"><feGaussianBlur stdDeviation="2" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>

        <g class="lanes">
          <rect x="15" y="18" width="970" height="102" rx="16" />
          <text x="30" y="16">知识规则路径</text>
          <rect x="255" y="210" width="735" height="430" rx="16" />
          <text x="270" y="207">模型推理与只读工具回环</text>
          <rect x="1005" y="125" width="385" height="655" rx="16" />
          <text x="1020" y="122">校验、HITL 与知识沉淀</text>
        </g>

        <g class="edges">
          <template v-for="edge in graph.edges" :key="`${edge.source}-${edge.target}-${edge.label}`">
            <path
              :d="edgePath(edge)"
              :class="{ active: isEdgeVisited(edge) }"
              :marker-end="isEdgeVisited(edge) ? 'url(#arrow-active)' : 'url(#arrow-idle)'"
            />
            <text v-if="edge.label" :x="labelPosition(edge).x" :y="labelPosition(edge).y" :class="{ active: isEdgeVisited(edge) }">
              {{ edge.label }}
            </text>
          </template>
        </g>

        <g
          v-for="node in layoutNodes"
          :key="node.id"
          class="svg-node"
          :class="[`kind-${node.kind}`, { visited: visited.has(node.id) }]"
          :transform="`translate(${node.x}, ${node.y})`"
        >
          <rect :width="nodeWidth" :height="nodeHeight" rx="13" />
          <circle cx="20" cy="20" r="6" />
          <text class="kind-label" x="34" y="24">{{ node.kind }}</text>
          <text class="node-label" x="14" y="47">{{ node.label }}</text>
          <text v-if="node.id === 'readonly_tools'" class="tool-choice" x="84" y="-10">
            {{ selectedTools.length ? `已选：${selectedTools.join('、')}` : '可查：知识、产品、规则' }}
          </text>
        </g>
      </svg>
    </div>
  </section>
</template>

<style scoped>
.panel-head small { display: block; margin-top: 5px; color: #678276; font-size: 11px; }
.graph-scroll { overflow: auto; padding-top: 14px; }
.intent-graph { display: block; min-width: 1180px; width: 100%; height: auto; }
.lanes rect { fill: #07130e; stroke: #1e372b; stroke-dasharray: 5 5; }
.lanes text { fill: #59766a; font: 10px Inter, "Microsoft YaHei", sans-serif; letter-spacing: .08em; }
.edges path { fill: none; stroke: #385247; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; opacity: .72; }
.edges path.active { stroke: #55e7a1; stroke-width: 2.2; opacity: 1; filter: url(#active-glow); }
.edges text { fill: #718e80; font: 10px Inter, "Microsoft YaHei", sans-serif; text-anchor: middle; paint-order: stroke; stroke: #07100d; stroke-width: 5px; }
.edges text.active { fill: #77efb4; }
.svg-node rect { fill: #09150f; stroke: #2a4337; stroke-width: 1.4; }
.svg-node circle { fill: #4c685b; }
.svg-node .kind-label { fill: #6f8a7d; font: 9px Inter, sans-serif; text-transform: uppercase; }
.svg-node .node-label { fill: #b6c9bf; font: 12px Inter, "Microsoft YaHei", sans-serif; font-weight: 700; }
.svg-node .tool-choice { fill: #a693e5; font: 10px Inter, "Microsoft YaHei", sans-serif; text-anchor: middle; }
.svg-node.visited rect { stroke: #55e7a1; stroke-width: 2; filter: url(#active-glow); }
.svg-node.visited circle { fill: #55e7a1; }
.svg-node.visited .node-label { fill: #effff7; }
.svg-node.kind-decision rect { fill: #122019; }
.svg-node.kind-human rect { fill: #271f0d; stroke: #806a2d; }
.svg-node.kind-tool rect { fill: #17132a; stroke: #5f5191; }
.svg-node.kind-knowledge rect { fill: #0b1d1d; stroke: #277774; }
.svg-node.kind-output rect, .svg-node.kind-end rect { fill: #103020; }
</style>
