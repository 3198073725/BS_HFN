<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import api from '../api/client'
import TeachingAttachmentPreview from '../components/TeachingAttachmentPreview.vue'
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
const pendingExam = ref(null)
const examAttachment = ref(null)
const existingAttachment = ref(null)
const removeAttachment = ref(false)
const attachmentPreview = ref(null)
const editingQuestionId = ref(null)
const records = ref([])
const paperContent = ref('')
const paperAttachment = ref(null)
const draftSaving = ref(false)
const gradingRecord = ref(null)
const gradeForm = reactive({ score: 0, teacher_comment: '' })
const recordFinished = computed(() => selectedRecord.value && selectedRecord.value.status !== 'DOING')
const answers = reactive({})
const remainingSeconds = ref(null)
const answerSaveState = ref('')
const examFormRef = ref(null)
const currentPage = ref(1)
const pageSize = 6
const examForm = reactive({
  exam_type: 'ONLINE',
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
  pendingExam.value = null
  examAttachment.value = null
  existingAttachment.value = exam?.attachment ? exam : null
  removeAttachment.value = false
  Object.assign(examForm, {
    exam_type: exam?.exam_type || 'ONLINE',
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

async function saveExam(publishPaper = false) {
  if (saving.value) return
  if (!pendingExam.value) {
    const valid = await examFormRef.value?.validate().catch(() => false)
    if (!valid) return
  }
  if (examForm.start_time && examForm.end_time && examForm.start_time >= examForm.end_time) {
    ElMessage.warning('结束时间必须晚于开始时间')
    return
  }
  if (examForm.exam_type === 'ATTACHMENT' && !examAttachment.value && (!existingAttachment.value || removeAttachment.value)) {
    ElMessage.warning('附件试卷需要上传试卷文件')
    return
  }
  saving.value = true
  try {
    const editing = Boolean(editingExamId.value)
    if (!pendingExam.value) {
      const response = editing
        ? await api.put(`/exams/${editingExamId.value}`, examForm)
        : await api.post('/exams', examForm)
      pendingExam.value = response.data
    }
    try {
      if (examAttachment.value) {
        const data = new FormData()
        data.append('attachment', examAttachment.value)
        const response = await api.post(`/exams/${pendingExam.value.id}/attachment`, data, { timeout: 60000 })
        pendingExam.value = response.data
      } else if (removeAttachment.value) {
        const response = await api.delete(`/exams/${pendingExam.value.id}/attachment`)
        pendingExam.value = response.data
      }
    } catch (error) {
      await load()
      ElMessage.warning(`测验草稿已保存，但附件处理失败：${error.message || '请重试'}；不会重复创建测验`)
      return
    }
    const savedExam = pendingExam.value
    createDialog.value = false
    if (savedExam.exam_type === 'ATTACHMENT') {
      exams.value = [savedExam, ...exams.value.filter((item) => item.id !== savedExam.id)]
      currentPage.value = 1
      ElMessage.success('附件试卷草稿已保存，无需录入在线题目')
      if (publishPaper === true) await changeStatus(savedExam, 'publish')
    } else if (editing) {
      const index = exams.value.findIndex((item) => item.id === savedExam.id)
      if (index >= 0) exams.value[index] = savedExam
      ElMessage.success('测验草稿已更新')
    } else {
      exams.value = [savedExam, ...exams.value.filter((item) => item.id !== savedExam.id)]
      currentPage.value = 1
      ElMessage.success('测验草稿已创建，请继续添加试题')
      await openQuestionManager(savedExam)
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
      `确认删除测验草稿“${exam.title}”？试题和附件也会一并删除。`,
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
      publishing ? '发布后不能再修改题目和附件，确认发布？' : '关闭后学生不能再开始或提交，确认关闭？',
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
    paperContent.value = response.data.record?.content || ''
    paperAttachment.value = null
    Object.keys(answers).forEach((key) => delete answers[key])
    restoreDraftAnswers(selectedRecord.value)
    if (recordFinished.value) {
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
    exams.value = exams.value.map((item) => item.id === selectedExam.value.id ? { ...item, record: started.data } : item)
    restoreDraftAnswers(started.data)
    if (started.data.status !== 'DOING') {
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
  if (saving.value || draftSaving.value || recordFinished.value) return
  if (selectedExam.value?.exam_type === 'ATTACHMENT' && !paperContent.value.trim() && !paperAttachment.value && !selectedRecord.value?.attachment) {
    ElMessage.warning('请输入答案或上传答卷附件')
    return
  }
  try {
    await ElMessageBox.confirm('提交后不能再次修改答案，确认交卷？', '提交测验', { type: 'warning' })
    saving.value = true
    const payload = selectedExam.value.questions.map((question) => ({
      question_id: question.id,
      answer: answers[question.id] || '',
    }))
    const response = selectedExam.value.exam_type === 'ATTACHMENT'
      ? await api.post(`/exams/${selectedExam.value.id}/submission`, paperPayload(), { timeout: 60000 })
      : await api.post(`/exams/${selectedExam.value.id}/submit`, { answers: payload })
    selectedRecord.value = response.data
    selectedExam.value.record = response.data
    stopCountdown()
    ElMessage.success(response.data.exam_type === 'ATTACHMENT' ? '答卷已提交，等待教师批改；提交后不可修改' : `交卷成功，得分 ${response.data.score}`)
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
  if (draftSaving.value || selectedRecord.value?.status !== 'DOING' || !selectedExam.value || remainingSeconds.value === 0) return false
  draftSaving.value = true
  const recordId = selectedRecord.value.id
  const uploadedFile = paperAttachment.value
  const savedContent = paperContent.value
  if (answerSaveTimer) window.clearTimeout(answerSaveTimer)
  answerSaveTimer = null
  const payload = Object.entries(answers).map(([questionId, answer]) => ({
    question_id: Number(questionId), answer,
  }))
  answerSaveState.value = '保存中…'
  try {
    const response = selectedExam.value.exam_type === 'ATTACHMENT'
      ? await api.put(`/exams/${selectedExam.value.id}/submission`, paperPayload(), { timeout: 60000 })
      : await api.put(`/exams/${selectedExam.value.id}/answers`, { answers: payload })
    if (selectedRecord.value?.id !== recordId || selectedRecord.value.status !== 'DOING') return false
    selectedRecord.value = { ...selectedRecord.value, ...response.data }
    selectedExam.value.record = selectedRecord.value
    exams.value = exams.value.map((item) => item.id === selectedExam.value.id ? { ...item, record: selectedRecord.value } : item)
    if (uploadedFile === paperAttachment.value) paperAttachment.value = null
    answerSaveState.value = '已自动保存'
    return true
  } catch (error) {
    if (selectedRecord.value?.id !== recordId || selectedRecord.value.status !== 'DOING') return false
    answerSaveState.value = '保存失败'
    ElMessage.error(error.message || '答案自动保存失败')
    return false
  } finally {
    draftSaving.value = false
    if (selectedExam.value?.exam_type === 'ATTACHMENT' && selectedRecord.value?.id === recordId && selectedRecord.value?.status === 'DOING'
      && savedContent !== paperContent.value && remainingSeconds.value !== 0) scheduleAnswerSave()
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
    const response = selectedExam.value.exam_type === 'ATTACHMENT'
      ? await api.post(`/exams/${selectedExam.value.id}/submission`, { content: paperContent.value })
      : await api.post(`/exams/${selectedExam.value.id}/submit`, { answers: payload })
    selectedRecord.value = response.data
    selectedExam.value.record = response.data
    answerSaveState.value = '已自动交卷'
    ElMessage.warning(response.data.exam_type === 'ATTACHMENT' ? '作答时间结束，已按保存的答卷自动交卷，等待教师批改' : `作答时间结束，系统已自动交卷，得分 ${response.data.score}`)
    await load()
  } catch (error) {
    ElMessage.error(error.message || '自动交卷失败，请重新打开测验确认状态')
  } finally {
    saving.value = false
  }
}

async function openRecords(exam) {
  selectedExam.value = exam
  gradingRecord.value = null
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
  pendingExam.value = null
  examAttachment.value = null
  existingAttachment.value = null
  removeAttachment.value = false
  Object.assign(examForm, {
    exam_type: 'ONLINE',
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

function selectExamAttachment(event) {
  const file = event.target.files?.[0]
  if (file && (file.size === 0 || file.size > 50 * 1024 * 1024)) {
    ElMessage.warning('请选择非空且不超过 50MB 的附件')
    event.target.value = ''
    return
  }
  examAttachment.value = file || null
  if (file) removeAttachment.value = false
}

function previewAttachment(exam) {
  const suffix = String(exam.attachment || '').split('.').pop()
  attachmentPreview.value?.open(`/exams/${exam.id}/attachment`, exam.attachment_name || `${exam.title} · 测验附件.${suffix}`)
}

function paperPayload() {
  const data = new FormData()
  data.append('content', paperContent.value)
  if (paperAttachment.value) data.append('attachment', paperAttachment.value)
  return data
}

function selectPaperAttachment(event) {
  const file = event.target.files?.[0]
  if (file && (file.size === 0 || file.size > 50 * 1024 * 1024)) {
    ElMessage.warning('请选择非空且不超过 50MB 的答卷附件')
    event.target.value = ''
    return
  }
  paperAttachment.value = file || null
  scheduleAnswerSave()
}

function previewPaperAnswer(record) {
  attachmentPreview.value?.open(`/exams/records/${record.id}/attachment`, record.attachment_name || '答卷附件')
}

function openPaperGrade(record) {
  gradingRecord.value = record
  gradeForm.score = record.score ?? 0
  gradeForm.teacher_comment = record.teacher_comment || ''
}

async function savePaperGrade() {
  if (!gradingRecord.value || saving.value) return
  saving.value = true
  try {
    const response = await api.put(`/exams/records/${gradingRecord.value.id}/grade`, gradeForm)
    records.value = records.value.map((record) => record.id === response.data.id ? response.data : record)
    gradingRecord.value = null
    ElMessage.success('批改结果已保存，学生答卷已锁定')
    await load()
  } catch (error) {
    ElMessage.error(error.message || '批改失败')
  } finally {
    saving.value = false
  }
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
        <p>{{ isTeacher ? '发布在线题目或附件试卷，查看答卷并批改成绩。' : '在线作答或提交附件答卷，查看测验结果。' }}</p>
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
          <span v-if="exam.exam_type === 'ATTACHMENT'">附件试卷 · 教师批改</span>
          <span v-else><strong>{{ exam.questions.length }}</strong> 题</span>
          <span><strong>{{ exam.total_score }}</strong> 分</span>
          <span><strong>{{ exam.time_limit_minutes || '—' }}</strong> 分钟</span>
        </div>
        <div class="exam-window">
          <span>{{ formatDate(exam.start_time) }}</span>
          <i>→</i>
          <span>{{ formatDate(exam.end_time) }}</span>
        </div>
        <div v-if="!isTeacher && exam.record && exam.record.status !== 'DOING'" class="exam-score-strip">
          <span>{{ exam.exam_type === 'ATTACHMENT' ? exam.record.status === 'GRADED' ? '已批改 · 答卷已锁定' : '已交卷 · 待教师批改' : `已完成 · ${exam.record.correct_count} 题正确` }}</span>
          <strong>{{ exam.record.score === null ? '待批改' : `${exam.record.score} / ${exam.total_score}` }}</strong>
        </div>
        <div class="exam-actions">
          <el-button v-if="exam.attachment" @click="previewAttachment(exam)">测验附件</el-button>
          <template v-if="isTeacher">
            <el-button v-if="exam.status === 'DRAFT'" plain @click="openExamForm(exam)">编辑信息</el-button>
            <el-button v-if="exam.status === 'DRAFT' && exam.exam_type !== 'ATTACHMENT'" type="primary" @click="openQuestionManager(exam)">
              试题管理
            </el-button>
            <el-button v-if="exam.status === 'DRAFT' && exam.exam_type === 'ATTACHMENT'" type="primary" @click="changeStatus(exam, 'publish')">发布试卷</el-button>
            <el-button v-if="exam.status === 'DRAFT'" type="danger" plain @click="deleteExam(exam)">
              删除草稿
            </el-button>
            <el-button v-if="exam.status === 'PUBLISHED'" type="warning" plain @click="changeStatus(exam, 'close')">
              关闭
            </el-button>
            <el-button v-if="exam.status !== 'DRAFT'" @click="openRecords(exam)">
              {{ exam.exam_type === 'ATTACHMENT' ? '答卷与批改' : '成绩' }}（{{ exam.submitted_count }}）
            </el-button>
          </template>
          <el-button
            v-else
            type="primary"
            :disabled="!exam.record && exam.availability !== 'AVAILABLE'"
            @click="openExam(exam)"
          >
            {{ exam.record && exam.record.status !== 'DOING' ? '查看结果' : exam.record ? '继续作答' : '开始测验' }}
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
      <p v-if="pendingExam" class="dialog-tip">草稿已保存，请重试附件处理，不会重复创建测验。</p>
      <el-form ref="examFormRef" :model="examForm" :rules="examRules" :disabled="Boolean(pendingExam)" label-position="top">
        <el-form-item label="测验方式">
          <el-radio-group v-model="examForm.exam_type">
            <el-radio value="ONLINE">在线试题（自动评分）</el-radio>
            <el-radio value="ATTACHMENT">附件试卷（教师批改）</el-radio>
          </el-radio-group>
        </el-form-item>
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
      <div class="teaching-attachment-field">
        <p>{{ examForm.exam_type === 'ATTACHMENT' ? '试卷附件（必选）' : '测验附件（可选）' }}</p>
        <div v-if="existingAttachment && !removeAttachment" class="attachment-existing">
          <el-button @click="previewAttachment(existingAttachment)">查看现有附件</el-button>
          <el-button :disabled="saving" @click="removeAttachment = true; examAttachment = null">移除附件</el-button>
        </div>
        <p v-if="removeAttachment" class="dialog-tip">保存后移除现有附件。<el-button link :disabled="saving" @click="removeAttachment = false">撤销</el-button></p>
        <label class="file-picker compact-file-picker">
          <input type="file" :disabled="saving" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.zip,.rar,.7z,.jpg,.jpeg,.png" @change="selectExamAttachment" />
          <span>{{ existingAttachment ? '替换附件' : '选择附件' }}</span>
          <strong>{{ examAttachment?.name || '最大 50MB' }}</strong>
        </label>
        <small>支持 PDF、Office 文档、文本、图片和压缩包；PDF、文本及图片可在线预览。发布后附件不可更改。</small>
        <small v-if="examForm.exam_type === 'ATTACHMENT'">上传文件即为完整试卷，无需录入在线题目；学生提交文字或答卷附件后由教师批改。</small>
      </div>
      <template #footer>
        <el-button :disabled="saving" @click="createDialog = false">取消</el-button>
        <el-button v-if="examForm.exam_type === 'ATTACHMENT'" :disabled="saving" @click="saveExam(false)">保存草稿</el-button>
        <el-button type="primary" :loading="saving" @click="saveExam(examForm.exam_type === 'ATTACHMENT')">
          {{ pendingExam ? '重试附件处理' : examForm.exam_type === 'ATTACHMENT' ? '保存并发布' : editingExamId ? '保存修改' : '保存并添加试题' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="questionDialog"
      class="question-manager-dialog"
      :title="`${selectedExam?.title || ''} · 试题管理`"
      width="min(1120px, calc(100vw - 32px))"
      align-center
      append-to-body
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
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
              <label>分值<el-input-number v-model="questionForm.score" :min="0.01" :max="999.99" :precision="2" aria-label="试题分值" /></label>
              <label>排序<el-input-number v-model="questionForm.sort_order" :min="0" :max="100000" aria-label="试题排序" /></label>
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
        <el-button :disabled="saving" @click="questionDialog = false">稍后继续</el-button>
        <el-button
          type="primary"
          :disabled="saving || !selectedExam?.questions.length || !scoreMatches"
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
      :close-on-click-modal="Boolean(recordFinished)"
      :close-on-press-escape="!saving && !draftSaving"
      :show-close="!saving && !draftSaving"
      @closed="handleTakeClosed"
    >
      <el-button v-if="selectedExam?.attachment" @click="previewAttachment(selectedExam)">查看测验附件</el-button>
      <div v-if="recordFinished && selectedExam?.exam_type === 'ATTACHMENT'" class="exam-result">
        <h3>{{ selectedRecord.status === 'GRADED' ? '教师已批改' : '已交卷，等待教师批改' }}</h3>
        <p>提交后答卷已锁定，不可修改。得分：{{ selectedRecord.score ?? '待批改' }} / {{ selectedRecord.total_score }}</p>
        <p class="paper-answer-content">{{ selectedRecord.content || '已通过附件提交答卷' }}</p>
        <p v-if="selectedRecord.teacher_comment">教师评语：{{ selectedRecord.teacher_comment }}</p>
        <el-button v-if="selectedRecord.attachment" @click="previewPaperAnswer(selectedRecord)">查看我的答卷附件</el-button>
      </div>
      <div v-else-if="recordFinished" class="exam-result">
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
          <span>{{ selectedExam.exam_type === 'ATTACHMENT' ? '附件试卷 · 教师批改' : `共 ${selectedExam.questions.length} 题` }} · 满分 {{ selectedExam.total_score }}</span>
          <strong v-if="remainingSeconds !== null" :class="{ urgent: remainingSeconds < 300 }">
            剩余 {{ formatDuration(remainingSeconds) }}
          </strong>
          <small v-if="answerSaveState" class="answer-save-state">{{ answerSaveState }}</small>
        </div>
        <div v-if="selectedExam.exam_type === 'ATTACHMENT'" class="teaching-attachment-field">
          <p>请查看教师试卷，填写答案或上传完成的答卷。</p>
          <el-input v-model="paperContent" type="textarea" :rows="10" maxlength="10000" show-word-limit placeholder="按题号填写答案，或上传答卷附件" @input="scheduleAnswerSave" />
          <el-button v-if="selectedRecord.attachment" @click="previewPaperAnswer(selectedRecord)">查看已保存答卷附件</el-button>
          <label class="file-picker compact-file-picker">
            <input type="file" :disabled="saving || draftSaving" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.zip,.rar,.7z,.jpg,.jpeg,.png" @change="selectPaperAttachment" />
            <span>选择答卷附件</span><strong>{{ paperAttachment?.name || selectedRecord.attachment_name || '最大 50MB' }}</strong>
          </label>
          <small>文字与附件自动保存；暂时离开后可继续，正式交卷后不可修改。</small>
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
        <el-button :disabled="saving || draftSaving" @click="takeDialog = false">{{ recordFinished ? '关闭' : '暂时离开' }}</el-button>
        <el-button
          v-if="!recordFinished"
          type="primary"
          :loading="saving"
          :disabled="draftSaving || remainingSeconds === 0"
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
          <template #default="scope">{{ scope.row.status === 'GRADED' ? '已批改' : scope.row.status === 'SUBMITTED' ? '已交卷' : '作答中' }}</template>
        </el-table-column>
        <el-table-column label="成绩" width="120">
          <template #default="scope">{{ scope.row.score === null ? '待批改' : scope.row.status !== 'DOING' ? `${scope.row.score} / ${scope.row.total_score}` : '—' }}</template>
        </el-table-column>
        <el-table-column v-if="selectedExam?.exam_type !== 'ATTACHMENT'" label="正确/错误" width="120">
          <template #default="scope">{{ scope.row.correct_count }} / {{ scope.row.wrong_count }}</template>
        </el-table-column>
        <el-table-column label="用时" width="100">
          <template #default="scope">{{ scope.row.duration_seconds === null ? '—' : formatDuration(scope.row.duration_seconds) }}</template>
        </el-table-column>
        <el-table-column label="提交时间" width="150">
          <template #default="scope">{{ formatDate(scope.row.submit_time) }}</template>
        </el-table-column>
        <el-table-column v-if="selectedExam?.exam_type === 'ATTACHMENT'" label="操作" width="170">
          <template #default="scope">
            <el-button v-if="scope.row.attachment" link @click="previewPaperAnswer(scope.row)">答卷附件</el-button>
            <el-button v-if="scope.row.status !== 'DOING'" link type="primary" @click="openPaperGrade(scope.row)">批改</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="还没有学生开始测验" :image-size="64" /></template>
      </el-table>
      <div v-if="gradingRecord" class="grade-panel">
        <div><strong>正在批改：{{ gradingRecord.student_name }}</strong><span>满分 {{ selectedExam.total_score }}</span></div>
        <p class="paper-answer-content">{{ gradingRecord.content || '学生通过附件提交答卷' }}</p>
        <div class="grade-form-row">
          <el-input-number v-model="gradeForm.score" :min="0" :max="selectedExam.total_score" :precision="2" />
          <el-input v-model="gradeForm.teacher_comment" maxlength="10000" placeholder="填写教师评语（可选）" />
          <el-button type="primary" :loading="saving" @click="savePaperGrade">保存批改</el-button>
        </div>
      </div>
    </el-dialog>
    <TeachingAttachmentPreview ref="attachmentPreview" />
  </section>
</template>
