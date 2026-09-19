<script setup>
import { ref } from 'vue'

defineProps({ busy: Boolean })
const emit = defineEmits(['submit', 'user-change'])
const userId = ref('zhangsan')
const text = ref('给我办理20元10GB流量包，下月生效')
const userProfiles = {
  zhangsan: '张三',
  lisi: '李四',
  laoxiao: '老肖',
}

function notifyUserChange() {
  emit('user-change', {
    user_id: userId.value,
    username: userProfiles[userId.value],
    role: '本人',
  })
}

function submit() {
  if (!text.value.trim()) return
  emit('submit', {
    text: text.value.trim(),
    user_id: userId.value,
    subject: {
      user_id: userId.value,
      username: userProfiles[userId.value],
      role: '本人',
    },
  })
}
</script>

<template>
  <section class="input-card">
    <div class="input-head">
      <div>
        <span class="eyebrow">NATURAL LANGUAGE</span>
        <h2>用户请求</h2>
      </div>
      <select v-model="userId" :disabled="busy" aria-label="演示用户" @change="notifyUserChange">
        <option value="zhangsan">张三</option>
        <option value="lisi">李四</option>
        <option value="laoxiao">老肖</option>
      </select>
    </div>
    <textarea v-model="text" :disabled="busy" rows="4" @keydown.ctrl.enter="submit" />
    <div class="input-actions">
      <span>Ctrl + Enter 运行</span>
      <button :disabled="busy || !text.trim()" @click="submit">
        {{ busy ? '识别中…' : '开始识别' }}
      </button>
    </div>
  </section>
</template>
