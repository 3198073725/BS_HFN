<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/client'
import { useDialogFocus } from '../utils/dialogFocus'

const visible = ref(false)
const restorePreviewFocus = useDialogFocus(visible)
const loading = ref(false)
const url = ref('')
const name = ref('')
const kind = ref('unsupported')
let requestId = 0

function clear() {
  requestId += 1
  if (url.value) URL.revokeObjectURL(url.value)
  url.value = ''
  loading.value = false
}

async function open(endpoint, filename) {
  clear()
  const id = requestId
  name.value = filename
  kind.value = 'unsupported'
  loading.value = true
  visible.value = true
  try {
    const blob = await api.get(endpoint, { responseType: 'blob', timeout: 60000 })
    if (id !== requestId || !visible.value) return
    const suffix = filename.split('.').pop()?.toLowerCase()
    kind.value = ['png', 'jpg', 'jpeg'].includes(suffix) ? 'image'
      : ['pdf', 'txt'].includes(suffix) ? 'document' : 'unsupported'
    url.value = URL.createObjectURL(blob)
  } catch (error) {
    if (id !== requestId) return
    visible.value = false
    ElMessage.error(error.message || '附件加载失败')
  } finally {
    if (id === requestId) loading.value = false
  }
}

function download() {
  if (!url.value) return
  const anchor = document.createElement('a')
  anchor.href = url.value
  anchor.download = name.value
  anchor.click()
}

defineExpose({ open })
onBeforeUnmount(clear)
</script>

<template>
  <el-dialog v-model="visible" :title="name" width="min(920px, 96vw)" align-center append-to-body @close="clear" @close-auto-focus="restorePreviewFocus">
    <div v-loading="loading" class="attachment-preview">
      <img v-if="url && kind === 'image'" :src="url" :alt="name" />
      <iframe v-else-if="url && kind === 'document'" :src="url" :title="name"></iframe>
      <el-empty v-else-if="!loading" description="该格式暂不支持在线预览，请下载后打开" :image-size="64" />
    </div>
    <template #footer>
      <el-button :disabled="!url" @click="download">下载附件</el-button>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>
