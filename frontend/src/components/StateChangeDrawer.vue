<script setup>
import { ref } from 'vue'

const props = defineProps({ result: Object })
const copied = ref(false)

async function copyThreadId() {
  if (!props.result?.thread_id) return
  await navigator.clipboard.writeText(props.result.thread_id)
  copied.value = true
  window.setTimeout(() => { copied.value = false }, 1500)
}
</script>

<template>
  <aside v-if="result" class="panel state-panel">
    <div class="panel-head">
      <h3>请求信封</h3>
      <div class="thread-id">
        <code>{{ result.thread_id }}</code>
        <button type="button" @click="copyThreadId">{{ copied ? '已复制' : '复制 ID' }}</button>
      </div>
    </div>
    <dl>
      <dt>原始输入</dt><dd>{{ result.original_input }}</dd>
      <dt>规范输入</dt><dd>{{ result.normalized_input }}</dd>
      <dt>缺失字段</dt><dd>{{ result.missing_fields?.join('、') || '无' }}</dd>
      <dt>歧义字段</dt><dd>{{ result.ambiguous_fields?.join('、') || '无' }}</dd>
      <dt>校验错误</dt><dd>{{ result.validation_errors?.join('；') || '无' }}</dd>
    </dl>
  </aside>
</template>

<style scoped>
.thread-id { display: flex; min-width: 0; align-items: center; gap: 7px; }
.thread-id code { overflow: hidden; max-width: 235px; color: #9fc7b2; font: 10px Consolas, monospace; text-overflow: ellipsis; white-space: nowrap; }
.thread-id button { padding: 5px 8px; border-radius: 6px; font-size: 10px; white-space: nowrap; }
</style>
