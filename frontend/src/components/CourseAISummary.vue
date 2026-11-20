<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api/client'
import MarkdownContent from './MarkdownContent.vue'

const props = defineProps({ videoId: { type: Number, required: true } })
const emit = defineEmits(['subtitle-ready'])
const state = ref(null)
const content = ref('')
const error = ref('')
const busy = ref(false)
let timer = null
let disposed = false
let sequence = 0
let subtitleNotified = false
const activeStatuses = ['QUEUED', 'EXTRACTING', 'SUBTITLING', 'SUMMARIZING']
const labels = { NOT_GENERATED: '尚未生成', LOCKED: '当前视频学习完成后解锁', QUEUED: '等待处理', EXTRACTING: '正在提取音频', SUBTITLING: '正在生成字幕', SUMMARIZING: '正在总结', DRAFT: '待教师审核', PUBLISHED: '已发布', FAILED: '生成失败', CANCELLED: '已取消' }
async function load() {
  const id = props.videoId
  const request = ++sequence
  clearTimeout(timer)
  try {
    const response = await api.get(`/videos/${id}/ai-summary`)
    if (disposed || request !== sequence || id !== props.videoId) return
    state.value = response.data
    if (activeStatuses.includes(state.value.status)) timer = setTimeout(load, 4000)
    else if (!busy.value) content.value = state.value.content || ''
    if (!subtitleNotified && ['SUMMARIZING', 'DRAFT', 'PUBLISHED'].includes(state.value.status)) {
      subtitleNotified = true
      emit('subtitle-ready')
    }
    error.value = ''
  } catch (e) {
    if (!disposed && request === sequence) error.value = e.message || '总结加载失败'
  }
}
async function generate() {
  const id = props.videoId
  try {
    await ElMessageBox.confirm(`仅生成当前视频“${state.value?.video_title || ''}”的字幕及 AI 总结。使用 DeepSeek API 额度，生成后需审核发布。`, '生成当前视频总结')
  } catch { return }
  if (disposed || id !== props.videoId) return
  busy.value = true
  subtitleNotified = false
  try {
    await api.post(`/videos/${id}/ai-summary/generate`)
    ElMessage.success('已开始生成，可稍后回来查看')
  } catch (e) { ElMessage.error(e.message || '生成失败') }
  finally { busy.value = false; if (!disposed) await load() }
}
async function save(publish) {
  busy.value = true
  try {
    await api.put(`/videos/${props.videoId}/ai-summary`, { content: content.value, publish })
    ElMessage.success(publish ? '总结已发布' : '草稿已保存')
  } catch (e) { ElMessage.error(e.message || '保存失败') }
  finally { busy.value = false; if (!disposed) await load() }
}
async function cancel() {
  busy.value = true
  try {
    await api.post(`/videos/${props.videoId}/ai-summary/cancel`)
    ElMessage.success('已取消当前视频任务')
  } catch (e) { ElMessage.error(e.message || '取消失败') }
  finally { busy.value = false; if (!disposed) await load() }
}
onMounted(load)
watch(() => props.videoId, () => { state.value = null; content.value = ''; subtitleNotified = false; void load() })
onBeforeUnmount(() => { disposed = true; ++sequence; clearTimeout(timer) })
</script>

<template>
  <section class="course-summary" aria-label="当前视频 AI 总结">
    <div class="summary-heading"><h2>视频 AI 总结</h2><span v-if="state">{{ labels[state.status] || '尚未生成' }}</span><el-button @click="load">刷新</el-button></div>
    <p v-if="error" role="alert">{{ error }}</p>
    <template v-else-if="state">
      <p class="summary-video-title">当前视频：{{ state.video_title }}</p>
      <p v-if="state.open_to_students" class="summary-access">本视频发布后的 AI 总结向所有学生开放，无需完成视频学习。</p>
      <p v-if="state.reason">{{ state.reason }}</p>
      <p v-else-if="!state.content">{{ state.manager ? '生成当前视频的字幕，整理知识点与复习建议，审核后发布给学生。' : '教师尚未发布当前视频总结。' }}</p>
      <p v-if="state.stale">当前视频资料已更新，总结需要重新生成。</p>
      <div v-if="activeStatuses.includes(state.status)" class="summary-progress" aria-live="polite">
        <el-progress :percentage="state.progress || 0" />
        <p>{{ state.progress_message || '当前视频任务等待处理' }}</p>
        <small>进度按处理阶段和已识别时间更新，不代表准确剩余时间。</small>
      </div>
      <p v-if="state.error_message" role="alert">{{ state.error_message }}</p>
      <template v-if="state.manager">
        <p v-if="!state.configured">请在后端 .env 配置 DEEPSEEK_API_KEY 并重启后端及工作进程。</p>
        <el-button :loading="busy" :disabled="!state.configured || activeStatuses.includes(state.status)" @click="generate">{{ state.content ? '重新生成当前视频总结' : '生成当前视频字幕及总结' }}</el-button>
        <el-button v-if="activeStatuses.includes(state.status)" :disabled="busy" @click="cancel">取消当前任务</el-button>
        <template v-if="state.content && !activeStatuses.includes(state.status)">
          <el-input v-model="content" type="textarea" :rows="12" maxlength="50000" aria-label="编辑当前视频总结" />
          <div class="summary-actions"><el-button :disabled="busy" @click="save(false)">保存草稿</el-button><el-button type="primary" :disabled="busy || state.stale" @click="save(true)">审核并发布</el-button></div>
        </template>
      </template>
      <MarkdownContent v-else-if="state.content" :content="state.content" class="summary-text" />
      <small>AI 生成内容经教师审核后提供，仅供学习参考。</small>
    </template>
  </section>
</template>

<style scoped>
.course-summary { box-sizing: border-box; width: 100%; min-width: 0; padding: 24px; margin: 0; border: 1px solid var(--line, #dbe2e8); border-radius: 8px; background: white; overflow-wrap: anywhere; }
.summary-heading, .summary-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.summary-heading h2 { margin: 0; flex: 1; font-size: 20px; }
.summary-heading span, small { color: #667687; }
.summary-text { margin-top: 24px; }
.el-textarea, .summary-actions { margin-top: 16px; }
small { display: block; margin-top: 16px; }
.summary-progress { margin: 16px 0; }
.summary-video-title { font-weight: 500; }
@media (max-width: 620px) {
  .course-summary { padding: 16px; }
  .summary-heading h2 { flex-basis: 100%; }
  .summary-heading > .el-button { margin-left: auto; }
}
</style>
