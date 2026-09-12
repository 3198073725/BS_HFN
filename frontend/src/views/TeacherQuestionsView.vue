<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref, watch } from 'vue'

import api from '../api/client'


const questions = ref([])
const loading = ref(false)
const statusFilter = ref('')
const answerDialog = ref(false)
const selectedQuestion = ref(null)
const submitting = ref(false)
const answerForm = reactive({ content: '' })
let requestSequence = 0

async function load() {
  const requestId = ++requestSequence
  const selectedStatus = statusFilter.value
  loading.value = true
  try {
    const response = await api.get('/questions', {
      params: selectedStatus ? { status: selectedStatus } : {},
    })
    if (requestId !== requestSequence) return
    questions.value = response.data
  } catch (error) {
    if (requestId === requestSequence) ElMessage.error(error.message || '答疑列表加载失败')
  } finally {
    if (requestId === requestSequence) loading.value = false
  }
}

function openAnswer(question) {
  selectedQuestion.value = question
  answerForm.content = question.answer?.content || ''
  answerDialog.value = true
}

async function submitAnswer() {
  const content = answerForm.content.trim()
  if (!content) {
    ElMessage.warning('请输入回答内容')
    return
  }
  submitting.value = true
  try {
    const method = selectedQuestion.value.answer ? 'put' : 'post'
    const response = await api[method](`/questions/${selectedQuestion.value.id}/answer`, { content })
    replaceQuestion(response.data)
    answerDialog.value = false
    ElMessage.success(method === 'post' ? '回答已提交' : '回答已更新')
  } catch (error) {
    ElMessage.error(error.message || '回答提交失败')
  } finally {
    submitting.value = false
  }
}

async function closeQuestion(question) {
  try {
    await ElMessageBox.confirm('关闭后该问题将不再接受回答，确认继续？', '关闭问题', {
      type: 'warning',
    })
    const response = await api.post(`/questions/${question.id}/close`)
    replaceQuestion(response.data)
    ElMessage.success('问题已关闭')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '问题关闭失败')
  }
}

function replaceQuestion(question) {
  const index = questions.value.findIndex((item) => item.id === question.id)
  if (index >= 0) questions.value[index] = question
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

watch(statusFilter, load)
onMounted(load)
</script>

<template>
  <section class="page-section teacher-questions">
    <div class="page-heading">
      <div>
        <p class="eyebrow">QUESTION CENTER</p>
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
      <article v-for="question in questions" :key="question.id" class="teacher-question-card">
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
              @click="openAnswer(question)"
            >
              {{ question.answer ? '编辑回答' : '回答问题' }}
            </el-button>
            <el-button v-if="question.status !== 'CLOSED'" @click="closeQuestion(question)">关闭</el-button>
          </div>
        </div>
      </article>
      <el-empty
        v-if="!loading && !questions.length"
        class="surface-card question-empty"
        description="当前筛选条件下没有问题"
      />
    </div>

    <el-dialog
      v-model="answerDialog"
      :title="selectedQuestion?.answer ? '编辑回答' : '回答问题'"
      width="min(620px, 92vw)"
      :close-on-click-modal="!submitting"
    >
      <div v-if="selectedQuestion" class="answer-dialog-context">
        <strong>{{ selectedQuestion.title }}</strong>
        <p>{{ selectedQuestion.content }}</p>
      </div>
      <el-input
        v-model="answerForm.content"
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
