<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import api from '../api/client'
import { useDialogFocus } from '../utils/dialogFocus'


const questions = ref([])
const loading = ref(false)
const loadError = ref('')
const statusFilter = ref('')
const answerDialog = ref(false)
const restoreAnswerFocus = useDialogFocus(answerDialog)
const selectedQuestion = ref(null)
const submitting = ref(false)
const closingId = ref(null)
const answerForm = reactive({ content: '' })
const currentPage = ref(1)
const pageSize = 8
let requestSequence = 0
let disposed = false

const pagedQuestions = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return questions.value.slice(start, start + pageSize)
})

async function load() {
  const requestId = ++requestSequence
  const selectedStatus = statusFilter.value
  loading.value = true
  loadError.value = ''
  try {
    const response = await api.get('/questions', {
      params: selectedStatus ? { status: selectedStatus } : {},
    })
    if (requestId !== requestSequence) return
    questions.value = response.data
    clampPage()
  } catch (error) {
    if (requestId === requestSequence) {
      loadError.value = error.message || '答疑列表加载失败'
      ElMessage.error(loadError.value)
    }
  } finally {
    if (requestId === requestSequence) loading.value = false
  }
}

function openAnswer(question) {
  if (submitting.value || closingId.value !== null) return
  selectedQuestion.value = question
  answerForm.content = question.answer?.content || ''
  answerDialog.value = true
}

async function submitAnswer() {
  if (submitting.value || !selectedQuestion.value) return
  const content = answerForm.content.trim()
  const questionId = selectedQuestion.value.id
  if (!content) {
    ElMessage.warning('请输入回答内容')
    return
  }
  submitting.value = true
  try {
    const method = selectedQuestion.value.answer ? 'put' : 'post'
    const response = await api[method](`/questions/${questionId}/answer`, { content })
    if (disposed) return
    replaceQuestion(response.data)
    answerDialog.value = false
    ElMessage.success(method === 'post' ? '回答已提交' : '回答已更新')
  } catch (error) {
    if (disposed) return
    ElMessage.error(error.message || '回答提交失败')
    if (error.status === 409 || error.code === 409) {
      try {
        const response = await api.get(`/questions/${questionId}`)
        if (disposed) return
        replaceQuestion(response.data)
        selectedQuestion.value = response.data
        if (response.data.status === 'CLOSED') answerDialog.value = false
      } catch { /* Keep the draft when state refresh also fails. */ }
    }
  } finally {
    submitting.value = false
  }
}

async function closeQuestion(question) {
  if (closingId.value !== null || submitting.value) return
  closingId.value = question.id
  try {
    await ElMessageBox.confirm('关闭后该问题将不再接受回答，确认继续？', '关闭问题', {
      type: 'warning',
    })
    if (disposed) return
    const response = await api.post(`/questions/${question.id}/close`)
    if (disposed) return
    replaceQuestion(response.data)
    ElMessage.success('问题已关闭')
  } catch (error) {
    if (!disposed && error !== 'cancel' && error !== 'close') {
      ElMessage.error(error.message || '问题关闭失败')
      if (error.status === 409 || error.code === 409) await load()
    }
  } finally {
    closingId.value = null
  }
}

function replaceQuestion(question) {
  if (loading.value) { void load(); return }
  const index = questions.value.findIndex((item) => item.id === question.id)
  if (index >= 0) {
    if (statusFilter.value && question.status !== statusFilter.value) questions.value.splice(index, 1)
    else questions.value[index] = question
  }
  clampPage()
}

function clampPage() {
  currentPage.value = Math.min(currentPage.value, Math.max(1, Math.ceil(questions.value.length / pageSize)))
}

function statusLabel(status) {
  return { WAITING: '等待回答', ANSWERED: '已回答', CLOSED: '已关闭' }[status] || status
}

function formatTime(seconds) {
  const value = Math.max(0, Math.floor(Number(seconds || 0)))
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`
}

function formatDate(value) {
  if (!value) return ''
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

watch(statusFilter, () => {
  currentPage.value = 1
  load()
})
onMounted(load)
onBeforeUnmount(() => { disposed = true; requestSequence += 1 })
</script>

<template>
  <section class="page-section teacher-questions">
    <div class="page-heading">
      <div>
        <p class="eyebrow">课程答疑</p>
        <h1>课程答疑</h1>
        <p>查看学生在视频时间点提出的问题，并给出正式回答。</p>
      </div>
      <div class="filter-control">
        <span>问题状态</span>
        <el-select v-model="statusFilter" placeholder="全部状态">
          <el-option label="全部状态" value="" />
          <el-option label="等待回答" value="WAITING" />
          <el-option label="已回答" value="ANSWERED" />
          <el-option label="已关闭" value="CLOSED" />
        </el-select>
      </div>
    </div>

    <div class="question-board" v-loading="loading">
      <el-result v-if="loadError" icon="error" title="答疑列表加载失败" :sub-title="loadError">
        <template #extra><el-button @click="load">重新加载</el-button></template>
      </el-result>
      <template v-else>
      <div
        class="stable-pagination-shell question-pagination-shell"
        :class="{ 'has-pagination': questions.length > pageSize }"
      >
      <div class="teacher-question-list stable-pagination-body">
      <article v-for="question in pagedQuestions" :key="question.id" class="teacher-question-card">
        <div class="teacher-question-top">
          <div>
            <span>{{ question.course_name }}</span>
            <i></i>
            <span>{{ question.video_title }} · {{ formatTime(question.video_time) }}</span>
          </div>
          <span :class="`question-status status-${question.status.toLowerCase()}`">
            {{ statusLabel(question.status) }}
          </span>
        </div>
        <h2>{{ question.title }}</h2>
        <p class="question-content">{{ question.content }}</p>
        <div v-if="question.answer" class="answer-box teacher-answer">
          <strong>我的回答</strong>
          <p>{{ question.answer.content }}</p>
        </div>
        <div class="teacher-question-footer">
          <span>{{ question.student_name }} · {{ formatDate(question.created_at) }}</span>
          <div>
            <el-button
              v-if="question.status !== 'CLOSED'"
              type="primary"
              :disabled="submitting || closingId !== null"
              @click="openAnswer(question)"
            >
              {{ question.answer ? '编辑回答' : '回答问题' }}
            </el-button>
            <el-button v-if="question.status !== 'CLOSED'" :disabled="submitting || closingId !== null" @click="closeQuestion(question)">关闭</el-button>
          </div>
        </div>
      </article>
      <el-empty
        v-if="!loading && !questions.length"
        class="surface-card question-empty"
        description="当前筛选条件下没有问题"
      />
      </div>
      <el-pagination
        v-if="questions.length > pageSize"
        v-model:current-page="currentPage"
        class="collection-pagination"
        background
        layout="prev, pager, next"
        :page-size="pageSize"
        :total="questions.length"
        aria-label="课程答疑分页"
      />
      </div>
      </template>
    </div>

    <el-dialog
      v-model="answerDialog"
      @close-auto-focus="restoreAnswerFocus"
      :title="selectedQuestion?.answer ? '编辑回答' : '回答问题'"
      width="min(620px, 92vw)"
      :close-on-click-modal="!submitting"
      :close-on-press-escape="!submitting"
      :show-close="!submitting"
    >
      <div v-if="selectedQuestion" class="answer-dialog-context">
        <strong>{{ selectedQuestion.title }}</strong>
        <p>{{ selectedQuestion.content }}</p>
      </div>
      <el-input
        v-model="answerForm.content"
        :disabled="submitting"
        type="textarea"
        :rows="7"
        maxlength="5000"
        show-word-limit
        placeholder="请输入清晰、准确的回答…"
      />
      <template #footer>
        <el-button :disabled="submitting" @click="answerDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitAnswer">
          {{ selectedQuestion?.answer ? '保存修改' : '提交回答' }}
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>
