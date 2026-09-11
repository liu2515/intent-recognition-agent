<script setup>
import { onMounted, ref } from 'vue'
import AgentBuildProcess from './components/AgentBuildProcess.vue'
import HitlDialog from './components/HitlDialog.vue'
import IntentGraphCanvas from './components/IntentGraphCanvas.vue'
import IntentInput from './components/IntentInput.vue'
import KnowledgeAdmin from './components/KnowledgeAdmin.vue'
import KnowledgeGraphCanvas from './components/KnowledgeGraphCanvas.vue'
import SixTupleTable from './components/SixTupleTable.vue'
import StateChangeDrawer from './components/StateChangeDrawer.vue'
import TranslationPath from './components/TranslationPath.vue'
import {
  approveKnowledgeCandidate,
  getGraphDefinition,
  getKnowledgeCandidates,
  getKnowledgeGraph,
  getKnowledgeRules,
  recognizeIntent,
  rejectKnowledgeCandidate,
  resumeIntent,
  syncKnowledgeGraph,
} from './api/intent'

const response = ref(null)
const graph = ref(null)
const busy = ref(false)
const error = ref('')
const activeUser = ref('')
const knowledgeRules = ref([])
const knowledgeCandidates = ref([])
const knowledgeGraph = ref(null)
const knowledgeBusy = ref(false)

onMounted(async () => {
  try {
    graph.value = await getGraphDefinition()
    await refreshKnowledge()
  } catch (event) { error.value = event.message }
})

async function refreshKnowledge() {
  knowledgeBusy.value = true
  try {
    const [rules, candidates, graphResult] = await Promise.all([
      getKnowledgeRules(),
      getKnowledgeCandidates(),
      getKnowledgeGraph(true),
    ])
    knowledgeRules.value = rules.items || []
    knowledgeCandidates.value = candidates.items || []
    knowledgeGraph.value = graphResult
  } finally { knowledgeBusy.value = false }
}

async function approveKnowledge({ templateId, reviewer }) {
  knowledgeBusy.value = true
  error.value = ''
  try {
    await approveKnowledgeCandidate(templateId, reviewer)
    await refreshKnowledge()
  } catch (event) { error.value = event.message; knowledgeBusy.value = false }
}

async function rejectKnowledge({ templateId, reviewer, reason }) {
  knowledgeBusy.value = true
  error.value = ''
  try {
    await rejectKnowledgeCandidate(templateId, reviewer, reason)
    await refreshKnowledge()
  } catch (event) { error.value = event.message; knowledgeBusy.value = false }
}

async function syncGraph() {
  knowledgeBusy.value = true
  error.value = ''
  try {
    const result = await syncKnowledgeGraph()
    if (result.status !== 'completed') error.value = result.error || 'Neo4j 尚未启用'
    await refreshKnowledge()
  } catch (event) { error.value = event.message; knowledgeBusy.value = false }
}

async function recognize(payload) {
  busy.value = true
  error.value = ''
  // 新请求开始时清空上一轮结果，避免网络请求期间继续显示旧六元组和旧执行路径。
  response.value = null
  activeUser.value = payload.user_id
  try {
    response.value = await recognizeIntent(payload)
    // 知识图谱刷新与本次 HITL 响应无关，不能继续占用识别中的 busy 状态。
    void refreshKnowledge().catch(event => { error.value = event.message })
  }
  catch (event) { error.value = event.message; response.value = null }
  finally { busy.value = false }
}

async function answer(value) {
  if (!response.value?.result?.thread_id) return
  busy.value = true
  error.value = ''
  try {
    response.value = await resumeIntent(response.value.result.thread_id, {
      user_id: activeUser.value,
      answer: value,
    })
    // 用户补充/确认已经返回后立即恢复交互；图谱在后台刷新即可。
    void refreshKnowledge().catch(event => { error.value = event.message })
  } catch (event) { error.value = event.message }
  finally { busy.value = false }
}
</script>

<template>
  <main class="intent-recognition-app">
    <header>
      <div class="brand-mark">M</div>
      <div><span class="eyebrow">MOBILE INTELLIGENCE</span><h1>意图识别工作台</h1></div>
      <div class="health"><i /> 意图识别服务就绪</div>
    </header>

    <IntentInput :busy="busy" @submit="recognize" />
    <p v-if="error" class="error-banner">{{ error }}</p>
    <TranslationPath :result="response?.result" />
    <HitlDialog :interrupt="response?.interrupt" :busy="busy" @answer="answer" />

    <div class="workspace-grid">
      <SixTupleTable :key="response?.result?.thread_id || 'empty'" :value="response?.result?.six_tuple" />
      <div class="side-column">
        <StateChangeDrawer :result="response?.result" />
        <AgentBuildProcess :trace="response?.trace" />
      </div>
    </div>
    <IntentGraphCanvas :key="response?.result?.thread_id || 'empty'" :graph="graph" :trace="response?.trace" />

    <div class="knowledge-workspace">
      <KnowledgeAdmin
        :rules="knowledgeRules"
        :candidates="knowledgeCandidates"
        :busy="knowledgeBusy"
        @approve="approveKnowledge"
        @reject="rejectKnowledge"
        @refresh="refreshKnowledge"
      />
      <KnowledgeGraphCanvas
        :graph="knowledgeGraph"
        :runtime-subject="response?.result?.six_tuple?.subject"
        :busy="knowledgeBusy"
        @refresh="refreshKnowledge"
        @sync="syncGraph"
      />
    </div>
  </main>
</template>

<style>
:root { color-scheme: dark; font-family: Inter, "Microsoft YaHei", sans-serif; background: #07100d; color: #e9f5ef; }
* { box-sizing: border-box; }
body { margin: 0; min-width: 320px; min-height: 100vh; background: radial-gradient(circle at 80% -10%, #15372b 0, transparent 35%), #07100d; }
button, input, textarea, select { font: inherit; }
button { cursor: pointer; }
.intent-recognition-app { width: min(1480px, calc(100% - 40px)); margin: 0 auto; padding: 24px 0 56px; }
header { display: flex; align-items: center; gap: 14px; margin-bottom: 22px; }
.brand-mark { width: 44px; height: 44px; display: grid; place-items: center; border-radius: 13px; font-weight: 900; color: #06100c; background: #4ee59a; box-shadow: 0 0 28px #4ee59a44; }
h1, h2, h3, h4, p { margin-top: 0; }
h1 { margin-bottom: 0; font-size: 22px; letter-spacing: .02em; }
h2 { margin: 3px 0 0; font-size: 20px; }
h3 { margin-bottom: 12px; font-size: 15px; }
.eyebrow { color: #58dda0; font-size: 10px; letter-spacing: .18em; font-weight: 800; }
.health { margin-left: auto; color: #aac2b6; font-size: 13px; }
.health i { display: inline-block; width: 8px; height: 8px; margin-right: 7px; border-radius: 50%; background: #4ee59a; box-shadow: 0 0 10px #4ee59a; }
.input-card, .path-card, .panel, .hitl-card { background: #0c1813dd; border: 1px solid #20362c; border-radius: 16px; box-shadow: 0 14px 45px #0005; }
.input-card { padding: 20px; }
.input-head, .panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
select, textarea, input { color: #e9f5ef; background: #07110d; border: 1px solid #29483a; border-radius: 9px; outline: none; }
select { padding: 8px 12px; }
textarea { width: 100%; margin-top: 16px; padding: 14px; resize: vertical; line-height: 1.65; }
textarea:focus, input:focus { border-color: #4ee59a; box-shadow: 0 0 0 3px #4ee59a18; }
.input-actions { display: flex; align-items: center; justify-content: flex-end; gap: 15px; margin-top: 12px; color: #6f8c7e; font-size: 12px; }
button { border: 1px solid #3ccb85; border-radius: 9px; padding: 9px 16px; color: #06100c; background: #4ee59a; font-weight: 750; }
button:disabled { opacity: .45; cursor: default; }
.path-card { padding: 14px 18px; margin-top: 14px; }
.path-row { display: flex; align-items: center; gap: 20px; margin-top: 10px; overflow-x: auto; }
.path-row > div { min-width: 125px; }
.path-row small { display: block; color: #718b7e; margin-bottom: 4px; }
.path-row strong { font-size: 13px; }
.path-row > span { color: #3f6653; }
.status-completed { color: #4ee59a; }
.status-needs_clarification, .status-requires_confirmation { color: #ffd36a; }
.status-invalid, .status-cancelled { color: #ff7c7c; }
.hitl-card { margin-top: 14px; padding: 20px; border-color: #806b30; background: #211c0d; }
.hitl-card h3 { margin: 5px 0 8px; color: #ffd36a; }
.hitl-card p { color: #eadfbf; }
.option-row, .answer-row { display: flex; gap: 10px; }
.answer-row input { flex: 1; padding: 10px 12px; }
.workspace-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr); gap: 14px; margin-top: 14px; align-items: start; }
.side-column { display: grid; gap: 14px; }
.panel { padding: 18px; min-width: 0; }
.panel-head { padding-bottom: 12px; border-bottom: 1px solid #1d3228; }
.panel-head h3 { margin: 0; }
.panel-head span { max-width: 60%; overflow: hidden; color: #718b7e; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.tuple-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }
.tuple-grid article { min-width: 0; padding: 13px; border: 1px solid #1d352a; border-radius: 11px; background: #08120e; }
.tuple-grid h4 { margin-bottom: 9px; color: #6ce9ab; font-size: 13px; }
pre { margin: 0; overflow: auto; color: #b8ccc2; font: 11px/1.5 Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
.empty { margin: 16px 0 0; color: #647d71; font-size: 13px; }
.state-panel dl { display: grid; grid-template-columns: 75px 1fr; gap: 9px; margin: 14px 0 0; font-size: 12px; }
.state-panel dt { color: #698276; }
.state-panel dd { margin: 0; overflow-wrap: anywhere; color: #bfd0c7; }
.trace-list { list-style: none; padding: 0; margin: 14px 0 0; }
.trace-list li { display: grid; grid-template-columns: 24px 1fr; align-items: center; gap: 8px; padding: 7px 0; color: #a9c0b5; border-bottom: 1px solid #172a21; font-size: 12px; }
.trace-list b { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; color: #07100d; background: #4ee59a; }
.graph-panel { margin-top: 14px; }
.knowledge-workspace { display: grid; grid-template-columns: minmax(360px, .9fr) minmax(0, 1.6fr); gap: 14px; margin-top: 14px; align-items: start; }
.node-flow { display: flex; align-items: center; gap: 7px; overflow-x: auto; padding: 18px 2px 5px; }
.graph-node { min-width: 118px; padding: 10px; border: 1px solid #273b32; border-radius: 9px; background: #09130f; opacity: .45; }
.graph-node.visited { border-color: #4ee59a; box-shadow: inset 0 0 18px #4ee59a12; opacity: 1; }
.graph-node small { display: block; color: #557164; font-size: 9px; text-transform: uppercase; }
.graph-node strong { display: block; margin-top: 4px; font-size: 12px; }
.connector { color: #345847; }
.error-banner { margin: 14px 0 0; padding: 12px 15px; border: 1px solid #733737; border-radius: 10px; color: #ffb0b0; background: #2b1010; }
@media (max-width: 1000px) { .knowledge-workspace { grid-template-columns: 1fr; } }
@media (max-width: 900px) { .workspace-grid { grid-template-columns: 1fr; } .tuple-grid { grid-template-columns: 1fr; } .intent-recognition-app { width: min(100% - 24px, 720px); } }
</style>
