<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import api from '../api/client'
import { useAuthStore } from '../stores/auth'


const auth = useAuthStore()
const isTeacher = computed(() => auth.user?.role === 'TEACHER')
const loading = ref(false)
const saving = ref(false)
const exams = ref([])
const courses = ref([])
const createDialog = ref(false)
const questionDialog = ref(false)
const takeDialog = ref(false)
const recordsDialog = ref(false)
const selectedExam = ref(null)
const selectedRecord = ref(null)
const editingExamId = ref(null)
const editingQuestionId = ref(null)
const records = ref([])
const answers = reactive({})
const remainingSeconds = ref(null)
const answerSaveState = ref('')
const examFormRef = ref(null)
const currentPage = ref(1)
const pageSize = 6
const examForm = reactive({
  course_id: null,
  title: '',
  description: '',
  total_score: 100,
  start_time: null,
  end_time: null,
  time_limit_minutes: 30,
})
const questionForm = reactive({
  question_type: 'SINGLE',
  content: '',
  option_a: '',
  option_b: '',
  option_c: '',
  option_d: '',
  correct_answer: 'A',
  score: 10,
  sort_order: 0,
})
const examRules = {
  course_id: [{ required: true, message: '请选择课程', trigger: 'change' }],
  title: [{ required: true, message: '请输入测验名称', trigger: 'blur' }],
}
let timer = null
let answerSaveTimer = null
let lastChanceSaveRequested = false

const questionScoreTotal = computed(() => (
  selectedExam.value?.questions?.reduce((sum, question) => sum + Number(question.score), 0) || 0
))
const scoreMatches = computed(() => (
  Math.abs(questionScoreTotal.value - Number(selectedExam.value?.total_score || 0)) < 0.001
))
const pagedExams = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return exams.value.slice(start, start + pageSize)
})

async function load() {
  loading.value = true
  try {
    if (isTeacher.value) {
      const [examResponse, courseResponse] = await Promise.all([
        api.get('/exams/manage'),
        api.get('/courses/mine'),
      ])
      exams.value = examResponse.data
      courses.value = courseResponse.data.filter((course) => course.status !== 'OFFLINE')
    } else {
      const response = await api.get('/exams')
      exams.value = response.data
    }
  } catch (error) {
    ElMessage.error(error.message || '测验列表加载失败')
  } finally {
    loading.value = false
  }
}

function openExamForm(exam = null) {
  editingExamId.value = exam?.id || null
  Object.assign(examForm, {
    course_id: exam?.course_id || null,
    title: exam?.title || '',
    description: exam?.description || '',
    total_score: exam?.total_score || 100,
    start_time: parseUtc(exam?.start_time),
    end_time: parseUtc(exam?.end_time),
    time_limit_minutes: exam?.time_limit_minutes || 30,
  })
  examFormRef.value?.clearValidate()
  createDialog.value = true
}

async function saveExam() {
  const valid = await examFormRef.value?.validate().catch(() => false)
  if (!valid || saving.value) return
  if (examForm.start_time && examForm.end_time && examForm.start_time >= examForm.end_time) {
    ElMessage.warning('结束时间必须晚于开始时间')
    return
  }
  saving.value = true
  try {
    const editing = Boolean(editingExamId.value)
    const response = editing
      ? await api.put(`/exams/${editingExamId.value}`, examForm)
      : await api.post('/exams', examForm)
    createDialog.value = false
    if (editing) {
      const index = exams.value.findIndex((item) => item.id === response.data.id)
      if (index >= 0) exams.value[index] = response.data
      ElMessage.success('测验草稿已更新')
    } else {
      exams.value.unshift(response.data)
      currentPage.value = 1
      ElMessage.success('测验草稿已创建，请继续添加试题')
      resetExamForm()
      await openQuestionManager(response.data)
    }
  } catch (error) {
    ElMessage.error(error.message || '测验保存失败')
  } finally {
    saving.value = false
  }
}

async function openQuestionManager(exam) {
  try {
    const response = await api.get(`/exams/${exam.id}`)
    selectedExam.value = response.data
    editingQuestionId.value = null
    resetQuestionForm()
    questionDialog.value = true
  } catch (error) {
    ElMessage.error(error.message || '测验详情加载失败')
  }
}

function openQuestionEditor(question) {
  editingQuestionId.value = question.id
  Object.assign(questionForm, {
    question_type: question.question_type,
    content: question.content,
    option_a: question.options?.A || '',
    option_b: question.options?.B || '',
    option_c: question.options?.C || '',
    option_d: question.options?.D || '',
    correct_answer: question.correct_answer,
    score: question.score,
    sort_order: question.sort_order,
  })
}

async function saveQuestion() {
  const content = questionForm.content.trim()
  if (!content) {
    ElMessage.warning('请输入题目内容')
    return
  }
  if (questionForm.question_type === 'SINGLE' && (!questionForm.option_a.trim() || !questionForm.option_b.trim())) {
    ElMessage.warning('单选题至少需要 A、B 两个选项')
    return
  }
  saving.value = true
  try {
    const editing = Boolean(editingQuestionId.value)
    const response = editing
      ? await api.put(`/exams/questions/${editingQuestionId.value}`, questionForm)
      : await api.post(`/exams/${selectedExam.value.id}/questions`, questionForm)
    if (editing) {
      const index = selectedExam.value.questions.findIndex((item) => item.id === response.data.id)
      if (index >= 0) selectedExam.value.questions[index] = response.data
    } else {
      selectedExam.value.questions.push(response.data)
    }
    selectedExam.value.questions.sort((a, b) => a.sort_order - b.sort_order || a.id - b.id)
    editingQuestionId.value = null
    resetQuestionForm()
    ElMessage.success(editing ? '试题已更新' : '试题已添加')
  } catch (error) {
    ElMessage.error(error.message || '试题保存失败')
  } finally {
    saving.value = false
  }
}

async function removeQuestion(question) {
  try {
    await ElMessageBox.confirm('确认删除这道试题？', '删除试题', { type: 'warning' })
    await api.delete(`/exams/questions/${question.id}`)
    selectedExam.value.questions = selectedExam.value.questions.filter((item) => item.id !== question.id)
    ElMessage.success('试题已删除')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '试题删除失败')
  }
}

async function deleteExam(exam) {
  try {
    await ElMessageBox.confirm(
      `确认删除测验草稿“${exam.title}”？试题也会一并删除。`,
      '删除测验草稿',
      { type: 'warning' },
    )
    await api.delete(`/exams/${exam.id}`)
    exams.value = exams.value.filter((item) => item.id !== exam.id)
    ElMessage.success('测验草稿已删除')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '测验删除失败')
  }
}

async function changeStatus(exam, action) {
  const publishing = action === 'publish'
  try {
    await ElMessageBox.confirm(
      publishing ? '发布后不能再修改题目，确认发布？' : '关闭后学生不能再开始或提交，确认关闭？',
      publishing ? '发布测验' : '关闭测验',
      { type: publishing ? 'info' : 'warning' },
    )
    await api.post(`/exams/${exam.id}/${action}`)
    ElMessage.success(publishing ? '测验已发布' : '测验已关闭')
    questionDialog.value = false
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '测验状态更新失败')
  }
}

async function openExam(exam) {
  try {
    const response = await api.get(`/exams/${exam.id}`)
    selectedExam.value = response.data
    selectedRecord.value = response.data.record
    Object.keys(answers).forEach((key) => delete answers[key])
    restoreDraftAnswers(selectedRecord.value)
    if (selectedRecord.value?.status === 'SUBMITTED') {
      takeDialog.value = true
      return
    }
    if (response.data.availability !== 'AVAILABLE') {
      ElMessage.warning(availabilityLabel(response.data.availability))
      return
    }
    const started = await api.post(`/exams/${exam.id}/start`)
    selectedRecord.value = started.data
    selectedExam.value.record = started.data
    restoreDraftAnswers(started.data)
    if (started.data.status === 'SUBMITTED') {
      takeDialog.value = true
      await load()
      return
    }
    startCountdown()
    takeDialog.value = true
  } catch (error) {
    ElMessage.error(error.message || '无法开始测验')
  }
}

async function submitExam() {
  try {
    await ElMessageBox.confirm('提交后不能再次修改答案，确认交卷？', '提交测验', { type: 'warning' })
    saving.value = true
    const payload = selectedExam.value.questions.map((question) => ({
      question_id: question.id,
      answer: answers[question.id] || '',
    }))
    const response = await api.post(`/exams/${selectedExam.value.id}/submit`, { answers: payload })
    selectedRecord.value = response.data
    selectedExam.value.record = response.data
    stopCountdown()
    ElMessage.success(`交卷成功，得分 ${response.data.score}`)
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '测验提交失败')
  } finally {
    saving.value = false
  }
}

function restoreDraftAnswers(record) {
  for (const item of record?.draft_answers || []) answers[item.question_id] = item.answer
}

function scheduleAnswerSave() {
  if (selectedRecord.value?.status !== 'DOING') return
  answerSaveState.value = '等待保存'
  if (answerSaveTimer) window.clearTimeout(answerSaveTimer)
  answerSaveTimer = window.setTimeout(() => void saveDraftAnswers(), 500)
}

async function saveDraftAnswers() {
  if (selectedRecord.value?.status !== 'DOING' || !selectedExam.value || remainingSeconds.value === 0) return false
  if (answerSaveTimer) window.clearTimeout(answerSaveTimer)
  answerSaveTimer = null
  const payload = Object.entries(answers).map(([questionId, answer]) => ({
    question_id: Number(questionId), answer,
  }))
  answerSaveState.value = '保存中…'
  try {
    const response = await api.put(`/exams/${selectedExam.value.id}/answers`, { answers: payload })
    selectedRecord.value = { ...selectedRecord.value, ...response.data }
    answerSaveState.value = '已自动保存'
    return true
  } catch (error) {
    answerSaveState.value = '保存失败'
    ElMessage.error(error.message || '答案自动保存失败')
    return false
  }
}

async function autoSubmitExam() {
  if (selectedRecord.value?.status !== 'DOING' || saving.value) return
  if (answerSaveTimer) window.clearTimeout(answerSaveTimer)
  answerSaveTimer = null
  saving.value = true
  try {
    const payload = selectedExam.value.questions.map((question) => ({
      question_id: question.id,
      answer: answers[question.id] || '',
    }))
    const response = await api.post(`/exams/${selectedExam.value.id}/submit`, { answers: payload })
    selectedRecord.value = response.data
    selectedExam.value.record = response.data
    answerSaveState.value = '已自动交卷'
    ElMessage.warning(`作答时间结束，系统已自动交卷，得分 ${response.data.score}`)
    await load()
  } catch (error) {
    ElMessage.error(error.message || '自动交卷失败，请重新打开测验确认状态')
  } finally {
    saving.value = false
  }
}

async function openRecords(exam) {
  selectedExam.value = exam
  try {
    const response = await api.get(`/exams/${exam.id}/records`)
    records.value = response.data
    recordsDialog.value = true
  } catch (error) {
    ElMessage.error(error.message || '测验记录加载失败')
  }
}

function startCountdown() {
  stopCountdown()
  lastChanceSaveRequested = false
  const startedAt = parseUtc(selectedRecord.value?.started_at)
  const endAt = parseUtc(selectedExam.value?.end_time)
  let deadline = endAt?.getTime() || null
  if (startedAt && selectedExam.value?.time_limit_minutes) {
    const limit = startedAt.getTime() + selectedExam.value.time_limit_minutes * 60000
    deadline = deadline ? Math.min(deadline, limit) : limit
  }
  if (!deadline) {
    remainingSeconds.value = null
    return
  }
  const update = () => {
    remainingSeconds.value = Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
    if (remainingSeconds.value === 1 && !lastChanceSaveRequested) {
      lastChanceSaveRequested = true
      void saveDraftAnswers()
    }
    if (remainingSeconds.value === 0) {
      stopCountdown()
      void autoSubmitExam()
    }
  }
  update()
  timer = window.setInterval(update, 1000)
}

function stopCountdown() {
  if (timer) window.clearInterval(timer)
  timer = null
}

function handleTakeClosed() {
  if (answerSaveTimer) window.clearTimeout(answerSaveTimer)
  answerSaveTimer = null
  void saveDraftAnswers()
  stopCountdown()
}

function resetExamForm() {
  editingExamId.value = null
  Object.assign(examForm, {
    course_id: null,
    title: '',
    description: '',
    total_score: 100,
    start_time: null,
    end_time: null,
    time_limit_minutes: 30,
  })
  examFormRef.value?.clearValidate()
}

function resetQuestionForm() {
  Object.assign(questionForm, {
    question_type: 'SINGLE',
    content: '',
    option_a: '',
    option_b: '',
    option_c: '',
    option_d: '',
    correct_answer: 'A',
    score: 10,
    sort_order: (selectedExam.value?.questions?.length || 0) + 1,
  })
}

function changeQuestionType(type) {
  resetQuestionForm()
  questionForm.question_type = type
  questionForm.correct_answer = type === 'JUDGE' ? 'TRUE' : 'A'
}

function cancelQuestionEdit() {
  editingQuestionId.value = null
  resetQuestionForm()
}

function parseUtc(value) {
  if (!value) return null
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  return new Date(normalized)
}

function formatDate(value) {
  const date = parseUtc(value)
  if (!date || Number.isNaN(date.getTime())) return '不限时间'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function formatDuration(seconds) {
  const value = Math.max(0, Number(seconds || 0))
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(Math.floor(value % 60)).padStart(2, '0')}`
}

function statusLabel(status) {
  return { DRAFT: '草稿', PUBLISHED: '已发布', CLOSED: '已关闭' }[status] || status
}

function availabilityLabel(status) {
  return {
    NOT_STARTED: '测验尚未开始',
    ENDED: '测验已经结束',
    CLOSED: '测验已关闭',
    AVAILABLE: '可以作答',
    DRAFT: '测验尚未发布',
  }[status] || status
}

function answerLabel(value) {
  return { TRUE: '正确', FALSE: '错误' }[value] || value || '未作答'
}

watch(() => exams.value.length, (total) => {
  currentPage.value = Math.min(currentPage.value, Math.max(1, Math.ceil(total / pageSize)))
})
onMounted(load)
onBeforeUnmount(() => {
  if (answerSaveTimer) window.clearTimeout(answerSaveTimer)
  void saveDraftAnswers()
  stopCountdown()
})
</script>

<template>
  <section class="page-section exam-center" v-loading="loading">
    <div class="page-heading">
      <div>
        <p class="eyebrow">在线测验</p>
        <h1>{{ isTeacher ? '测验管理' : '在线测验' }}</h1>
        <p>{{ isTeacher ? '编排客观题、发布测验并查看学生成绩。' : '完成课程测验，提交后即时查看自动评分结果。' }}</p>
      </div>
      <el-button v-if="isTeacher" type="primary" size="large" @click="openExamForm()">
        ＋ 创建测验
      </el-button>
    </div>

    <div class="exam-grid">
      <article v-for="exam in pagedExams" :key="exam.id" class="exam-card">
        <div class="exam-card-top">
          <span>{{ exam.course_name }}</span>
          <i :class="`exam-state state-${exam.status.toLowerCase()}`">{{ statusLabel(exam.status) }}</i>
        </div>
        <h2>{{ exam.title }}</h2>
        <p>{{ exam.description || '教师暂未填写测验说明。' }}</p>
        <div class="exam-facts">
          <span><strong>{{ exam.questions.length }}</strong> 题</span>
          <span><strong>{{ exam.total_score }}</strong> 分</span>
          <span><strong>{{ exam.time_limit_minutes || '—' }}</strong> 分钟</span>
        </div>
        <div class="exam-window">
          <span>{{ formatDate(exam.start_time) }}</span>
          <i>→</i>
          <span>{{ formatDate(exam.end_time) }}</span>
        </div>
        <div v-if="!isTeacher && exam.record?.status === 'SUBMITTED'" class="exam-score-strip">
          <span>已完成 · {{ exam.record.correct_count }} 题正确</span>
          <strong>{{ exam.record.score }} / {{ exam.total_score }}</strong>
        </div>
        <div class="exam-actions">
          <template v-if="isTeacher">
            <el-button v-if="exam.status === 'DRAFT'" plain @click="openExamForm(exam)">编辑信息</el-button>
            <el-button v-if="exam.status === 'DRAFT'" type="primary" @click="openQuestionManager(exam)">
              试题管理
            </el-button>
            <el-button v-if="exam.status === 'DRAFT'" type="danger" plain @click="deleteExam(exam)">
              删除草稿
            </el-button>
            <el-button v-if="exam.status === 'PUBLISHED'" type="warning" plain @click="changeStatus(exam, 'close')">
              关闭
            </el-button>
            <el-button v-if="exam.status !== 'DRAFT'" @click="openRecords(exam)">
              成绩（{{ exam.submitted_count }}）
            </el-button>
          </template>
          <el-button
            v-else
            type="primary"
            :disabled="!exam.record && exam.availability !== 'AVAILABLE'"
            @click="openExam(exam)"
          >
            {{ exam.record?.status === 'SUBMITTED' ? '查看结果' : exam.record ? '继续作答' : '开始测验' }}
          </el-button>
          <span v-if="!isTeacher && !exam.record">{{ availabilityLabel(exam.availability) }}</span>
        </div>
      </article>
      <el-empty
        v-if="!loading && !exams.length"
        class="surface-card exam-empty"
        :description="isTeacher ? '还没有测验，先创建一份草稿吧' : '当前没有可参加的课程测验'"
      />
      <el-pagination
        v-if="exams.length > pageSize"
        v-model:current-page="currentPage"
        class="collection-pagination"
        background
        layout="prev, pager, next"
        :page-size="pageSize"
        :total="exams.length"
        aria-label="测验列表分页"
      />
    </div>

    <el-dialog
      v-model="createDialog"
      :title="editingExamId ? '编辑测验草稿' : '创建测验草稿'"
      width="min(640px, 94vw)"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      @closed="resetExamForm"
    >
      <el-form ref="examFormRef" :model="examForm" :rules="examRules" label-position="top">
        <el-form-item label="所属课程" prop="course_id">
          <el-select v-model="examForm.course_id" placeholder="请选择课程" style="width: 100%">
            <el-option v-for="course in courses" :key="course.id" :label="course.name" :value="course.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="测验名称" prop="title">
          <el-input v-model.trim="examForm.title" maxlength="200" show-word-limit placeholder="例如：第一章基础测验" />
        </el-form-item>
        <el-form-item label="测验说明">
          <el-input v-model.trim="examForm.description" type="textarea" :rows="3" maxlength="10000" placeholder="填写作答要求…" />
        </el-form-item>
        <div class="exam-form-row three-columns">
          <el-form-item label="测验总分">
            <el-input-number v-model="examForm.total_score" :min="0.01" :max="9999.99" :precision="2" />
          </el-form-item>
          <el-form-item label="限时（分钟）">
            <el-input-number v-model="examForm.time_limit_minutes" :min="1" :max="1440" />
          </el-form-item>
        </div>
        <div class="exam-form-row">
          <el-form-item label="开始时间">
            <el-date-picker v-model="examForm.start_time" type="datetime" placeholder="立即开始" style="width: 100%" />
          </el-form-item>
          <el-form-item label="结束时间">
            <el-date-picker v-model="examForm.end_time" type="datetime" placeholder="不限结束时间" style="width: 100%" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="createDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveExam">
          {{ editingExamId ? '保存修改' : '保存并添加试题' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="questionDialog"
      :title="`${selectedExam?.title || ''} · 试题管理`"
      width="min(980px, 96vw)"
      @closed="load"
    >
      <div v-if="selectedExam" class="question-manager">
        <div class="score-check" :class="{ matched: scoreMatches }">
          <span>试题分值合计</span>
          <strong>{{ questionScoreTotal }} / {{ selectedExam.total_score }}</strong>
          <small>{{ scoreMatches ? '分值已匹配，可以发布' : '发布前需要与总分一致' }}</small>
        </div>
        <div class="question-manager-layout">
          <div class="exam-question-list">
            <article v-for="(question, index) in selectedExam.questions" :key="question.id">
              <span>{{ index + 1 }}</span>
              <div>
                <strong>{{ question.content }}</strong>
                <small>{{ question.question_type === 'SINGLE' ? '单选题' : '判断题' }} · {{ question.score }} 分 · 答案 {{ answerLabel(question.correct_answer) }}</small>
              </div>
              <div class="question-list-actions">
                <el-button link type="primary" @click="openQuestionEditor(question)">编辑</el-button>
                <el-button link type="danger" @click="removeQuestion(question)">删除</el-button>
              </div>
            </article>
            <el-empty v-if="!selectedExam.questions.length" description="还没有试题" :image-size="58" />
          </div>
          <div class="question-create-panel">
            <h3>{{ editingQuestionId ? '编辑试题' : '添加试题' }}</h3>
            <el-select v-model="questionForm.question_type" style="width: 100%" @change="changeQuestionType">
              <el-option label="单选题" value="SINGLE" />
              <el-option label="判断题" value="JUDGE" />
            </el-select>
            <el-input v-model.trim="questionForm.content" type="textarea" :rows="3" maxlength="10000" placeholder="请输入题目内容" />
            <template v-if="questionForm.question_type === 'SINGLE'">
              <el-input v-model.trim="questionForm.option_a" placeholder="选项 A" />
              <el-input v-model.trim="questionForm.option_b" placeholder="选项 B" />
              <el-input v-model.trim="questionForm.option_c" placeholder="选项 C（可选）" />
              <el-input v-model.trim="questionForm.option_d" placeholder="选项 D（可选）" />
              <el-select v-model="questionForm.correct_answer" placeholder="正确答案" style="width: 100%">
                <el-option v-for="key in ['A', 'B', 'C', 'D']" :key="key" :label="`正确答案 ${key}`" :value="key" />
              </el-select>
            </template>
            <el-radio-group v-else v-model="questionForm.correct_answer">
              <el-radio-button value="TRUE">正确</el-radio-button>
              <el-radio-button value="FALSE">错误</el-radio-button>
            </el-radio-group>
            <div class="question-number-row">
              <el-input-number v-model="questionForm.score" :min="0.01" :max="999.99" :precision="2" />
              <el-input-number v-model="questionForm.sort_order" :min="0" :max="100000" />
            </div>
            <div class="question-editor-actions">
              <el-button v-if="editingQuestionId" :disabled="saving" @click="cancelQuestionEdit">取消编辑</el-button>
              <el-button type="primary" :loading="saving" @click="saveQuestion">
                {{ editingQuestionId ? '保存试题修改' : '添加到测验' }}
              </el-button>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="questionDialog = false">稍后继续</el-button>
        <el-button
          type="primary"
          :disabled="!selectedExam?.questions.length || !scoreMatches"
          @click="changeStatus(selectedExam, 'publish')"
        >
          发布测验
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="takeDialog"
      :title="selectedExam?.title"
      width="min(860px, 96vw)"
      :close-on-click-modal="selectedRecord?.status === 'SUBMITTED'"
      @closed="handleTakeClosed"
    >
      <div v-if="selectedRecord?.status === 'SUBMITTED'" class="exam-result">
        <div class="result-score">
          <span>本次得分</span>
          <strong>{{ selectedRecord.score }}</strong>
          <small>/ {{ selectedRecord.total_score }}</small>
        </div>
        <p>答对 {{ selectedRecord.correct_count }} 题，答错或未答 {{ selectedRecord.wrong_count }} 题，用时 {{ formatDuration(selectedRecord.duration_seconds) }}</p>
        <article v-for="(answer, index) in selectedRecord.answers" :key="answer.question.id" class="result-answer">
          <span :class="answer.is_correct ? 'correct' : 'wrong'">{{ answer.is_correct ? '✓' : '×' }}</span>
          <div>
            <strong>{{ index + 1 }}. {{ answer.question.content }}</strong>
            <p>你的答案：{{ answerLabel(answer.student_answer) }} · 正确答案：{{ answerLabel(answer.question.correct_answer) }}</p>
          </div>
        </article>
      </div>
      <div v-else-if="selectedExam" class="exam-paper">
        <div class="exam-paper-bar">
          <span>共 {{ selectedExam.questions.length }} 题 · 满分 {{ selectedExam.total_score }}</span>
          <strong v-if="remainingSeconds !== null" :class="{ urgent: remainingSeconds < 300 }">
            剩余 {{ formatDuration(remainingSeconds) }}
          </strong>
          <small v-if="answerSaveState" class="answer-save-state">{{ answerSaveState }}</small>
        </div>
        <article v-for="(question, index) in selectedExam.questions" :key="question.id" class="paper-question">
          <h3><span>{{ index + 1 }}</span>{{ question.content }} <small>{{ question.score }} 分</small></h3>
          <el-radio-group v-if="question.question_type === 'SINGLE'" v-model="answers[question.id]" class="answer-options" @change="scheduleAnswerSave">
            <el-radio v-for="(option, key) in question.options" :key="key" :value="key" border>
              <strong>{{ key }}</strong>{{ option }}
            </el-radio>
          </el-radio-group>
          <el-radio-group v-else v-model="answers[question.id]" class="answer-options judge-options" @change="scheduleAnswerSave">
            <el-radio value="TRUE" border>正确</el-radio>
            <el-radio value="FALSE" border>错误</el-radio>
          </el-radio-group>
        </article>
      </div>
      <template #footer>
        <el-button @click="takeDialog = false">{{ selectedRecord?.status === 'SUBMITTED' ? '关闭' : '暂时离开' }}</el-button>
        <el-button
          v-if="selectedRecord?.status !== 'SUBMITTED'"
          type="primary"
          :loading="saving"
          :disabled="remainingSeconds === 0"
          @click="submitExam"
        >
          提交测验
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="recordsDialog" :title="`${selectedExam?.title || ''} · 成绩记录`" width="min(820px, 96vw)">
      <el-table :data="records" max-height="440">
        <el-table-column prop="student_name" label="学生" min-width="130" />
        <el-table-column label="状态" width="100">
          <template #default="scope">{{ scope.row.status === 'SUBMITTED' ? '已交卷' : '作答中' }}</template>
        </el-table-column>
        <el-table-column label="成绩" width="120">
          <template #default="scope">{{ scope.row.status === 'SUBMITTED' ? `${scope.row.score} / ${scope.row.total_score}` : '—' }}</template>
        </el-table-column>
        <el-table-column label="正确/错误" width="120">
          <template #default="scope">{{ scope.row.correct_count }} / {{ scope.row.wrong_count }}</template>
        </el-table-column>
        <el-table-column label="用时" width="100">
          <template #default="scope">{{ scope.row.duration_seconds === null ? '—' : formatDuration(scope.row.duration_seconds) }}</template>
        </el-table-column>
        <el-table-column label="提交时间" width="150">
          <template #default="scope">{{ formatDate(scope.row.submit_time) }}</template>
        </el-table-column>
        <template #empty><el-empty description="还没有学生开始测验" :image-size="64" /></template>
      </el-table>
    </el-dialog>
  </section>
</template>
