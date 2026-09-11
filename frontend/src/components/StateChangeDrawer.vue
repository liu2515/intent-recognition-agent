<script setup>
defineProps({ result: Object })
</script>

<template>
  <aside v-if="result" class="panel state-panel">
    <div class="panel-head"><h3>请求信封</h3><span>{{ result.thread_id }}</span></div>
    <dl>
      <dt>原始输入</dt><dd>{{ result.original_input }}</dd>
      <dt>规范输入</dt><dd>{{ result.normalized_input }}</dd>
      <dt>缺失字段</dt><dd>{{ result.missing_fields?.join('、') || '无' }}</dd>
      <dt>歧义字段</dt><dd>{{ result.ambiguous_fields?.join('、') || '无' }}</dd>
      <dt>校验错误</dt><dd>{{ result.validation_errors?.join('；') || '无' }}</dd>
    </dl>
  </aside>
</template>
