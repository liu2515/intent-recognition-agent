<script setup>
import { ref, watch } from 'vue'

const props = defineProps({ interrupt: Object, busy: Boolean })
const emit = defineEmits(['answer'])
const answer = ref('')
const validationError = ref('')
watch(() => props.interrupt, () => { answer.value = ''; validationError.value = '' })

function submitAnswer() {
  const value = answer.value.trim()
  if (!value) return
  if (
    props.interrupt?.fields?.includes('subject.mobile_number')
    && !/1[3-9]\d{9}/.test(value)
  ) {
    validationError.value = '请输入11位中国大陆手机号，号码需以 13 至 19 开头。'
    return
  }
  validationError.value = ''
  emit('answer', value)
}
</script>

<template>
  <section v-if="interrupt" class="hitl-card">
    <span class="eyebrow">HUMAN IN THE LOOP</span>
    <h3>{{ interrupt.kind === 'confirmation' ? '等待业务确认' : '需要补充信息' }}</h3>
    <p>{{ interrupt.question }}</p>
    <div v-if="interrupt.options?.length" class="option-row">
      <button v-for="option in interrupt.options" :key="option" :disabled="busy" @click="emit('answer', option)">
        {{ option }}
      </button>
    </div>
    <div v-else class="answer-row">
      <input v-model="answer" :disabled="busy" placeholder="输入补充信息" @keyup.enter="submitAnswer" />
      <button :disabled="busy || !answer.trim()" @click="submitAnswer">提交</button>
    </div>
    <p v-if="validationError" class="validation-error">{{ validationError }}</p>
  </section>
</template>

<style scoped>
.validation-error { margin: 9px 0 0; color: #ffb0b0; font-size: 12px; }
</style>
