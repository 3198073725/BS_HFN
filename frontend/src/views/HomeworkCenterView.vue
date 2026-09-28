<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import api from '../api/client'
import OverflowText from '../components/OverflowText.vue'
import { useDialogFocus } from '../utils/dialogFocus'
import { useAuthStore } from '../stores/auth'


const auth = useAuthStore()
const isTeacher = computed(() => auth.user?.role === 'TEACHER')
const loading = ref(false)
const loadError = ref('')
const submissionsLoading = ref(false)
const submissionsError = ref('')
const requirementsDialog = ref(false)
const requirementsHomework = ref(null)
const homeworks = ref([])
const courses = ref([])
const createDialog = ref(false)
const submissionDialog = ref(false)
const gradeDialog = ref(false)
const previewDialog = ref(false)
const teacherCommentDialog = ref(false)
const restoreRequirementsFocus = useDialogFocus(requirementsDialog)
const restoreCreateFocus = useDialogFocus(createDialog)
const restoreSubmissionFocus = useDialogFocus(submissionDialog)
const restoreGradeFocus = useDialogFocus(gradeDialog)
const restorePreviewFocus = useDialogFocus(previewDialog)
const restoreTeacherCommentFocus = useDialogFocus(teacherCommentDialog)
const previewLoading = ref(false)
const previewUrl = ref('')
const previewName = ref('')
const previewKind = ref('unsupported')
const selectedHomework = ref(null)
const selectedSubmission = ref(null)
const commentHomework = ref(null)
const homeworkAttachment = ref(null)
const submissionAttachment = ref(null)
const submissions = ref([])
const saving = ref(false)
const currentPage = ref(1)
const pageSize = 6
const filterCourse = ref('')
const filterStatus = ref('')
const keywordInput = ref('')
const keyword = ref('')
const homeworkFormRef = ref(null)
const pendingHomeworkId = ref(null)
const editingHomeworkId = ref(null)
const existingTeacherAttachment = ref(null)
const deadlineMode = ref('UNLIMITED')
const submissionContentSaved = ref(null)
const now = ref(Date.now())
const selectedHomeworkOpen = computed(() => (
  Boolean(selectedHomework.value) && isHomeworkOpen(selectedHomework.value)
))
let deadlineTicker = null
let previewRequestSequence = 0
let submissionsRequestSequence = 0
const homeworkForm = reactive({
  course_id: null,
  title: '',
  description: '',
  deadline: null,
  total_score: 100,
})
const submissionForm = reactive({ content: '' })
const gradeForm = reactive({ score: 0, teacher_comment: '' })
const homeworkRules = {
  course_id: [{ required: true, message: '请选择课程', trigger: 'change' }],
  title: [
    { required: true, message: '请输入作业标题', trigger: 'blur' },
    { max: 200, message: '作业标题不能超过 200 位', trigger: 'blur' },
  ],
  description: [{ required: true, message: '请输入作业要求', trigger: 'blur' }],
}

const homeworkCourseOptions = computed(() => {
  const options = new Map()
  homeworks.value.forEach((item) => options.set(courseFilterKey(item), item.course_name || '未命名课程'))
  return [...options].map(([value, label]) => ({ value, label }))
})
const filteredHomeworks = computed(() => {
  const query = keyword.value.toLocaleLowerCase()
  return homeworks.value.filter((item) => (
    (!filterCourse.value || courseFilterKey(item) === filterCourse.value)
    && (!filterStatus.value || homeworkLifecycle(item) === filterStatus.value)
    && (!query || `${item.title || ''} ${item.description || ''} ${item.course_name || ''}`.toLocaleLowerCase().includes(query))
  ))
})
const hasActiveFilters = computed(() => Boolean(filterCourse.value || filterStatus.value || keyword.value))
const pagedHomeworks = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredHomeworks.value.slice(start, start + pageSize)
})

function courseFilterKey(item) {
  return item.course_id == null ? `name:${item.course_name || ''}` : `id:${item.course_id}`
}

function homeworkLifecycle(homework) {
  if (homework.status === 'DRAFT') return 'DRAFT'
  if (homework.status === 'CLOSED') return 'CLOSED'
  const deadline = parseUtc(homework.deadline)
  if (homework.availability === 'ENDED' || (deadline && deadline.getTime() <= now.value)) return 'ENDED'
  return 'OPEN'
}

function applyFilters() {
  keyword.value = keywordInput.value.trim()
  currentPage.value = 1
}

function resetFilters() {
  filterCourse.value = ''
  filterStatus.value = ''
  keywordInput.value = ''
  keyword.value = ''
  currentPage.value = 1
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    if (isTeacher.value) {
      const [homeworkResponse, courseResponse] = await Promise.all([
        api.get('/homeworks/manage'),
        api.get('/courses/mine'),
      ])
      homeworks.value = homeworkResponse.data
      courses.value = courseResponse.data.filter((course) => course.status !== 'OFFLINE')
    } else {
      const response = await api.get('/homeworks')
      homeworks.value = response.data
    }
  } catch (error) {
    loadError.value = error.message || '作业列表加载失败'
    ElMessage.error(error.message || '作业列表加载失败')
  } finally {
    loading.value = false
  }
}

function openHomework(homework = null) {
  editingHomeworkId.value = homework?.id || null
  pendingHomeworkId.value = null
  existingTeacherAttachment.value = homework?.attachment ? homework : null
  deadlineMode.value = homework?.deadline ? 'LIMITED' : 'UNLIMITED'
  Object.assign(homeworkForm, {
    course_id: homework?.course_id || null,
    title: homework?.title || '',
    description: homework?.description || '',
    deadline: parseUtc(homework?.deadline),
    total_score: homework?.total_score || 100,
  })
  homeworkAttachment.value = null
  homeworkFormRef.value?.clearValidate()
  createDialog.value = true
}

async function saveHomework() {
  if (saving.value) return
  if (!pendingHomeworkId.value) {
    const valid = await homeworkFormRef.value?.validate().catch(() => false)
    if (!valid) return
  } else if (!homeworkAttachment.value) {
    ElMessage.warning('请重新选择附件后再重试上传')
    return
  }

  saving.value = true
  let committedAction = ''
  try {
    if (!pendingHomeworkId.value) {
      const payload = {
        ...homeworkForm,
        deadline: deadlineMode.value === 'LIMITED' ? homeworkForm.deadline : null,
      }
      if (deadlineMode.value === 'LIMITED' && !payload.deadline) {
        ElMessage.warning('请选择作业截止时间，或改为不限时作业')
        return
      }
      const response = editingHomeworkId.value
        ? await api.put(`/homeworks/${editingHomeworkId.value}`, payload)
        : await api.post('/homeworks', payload)
      pendingHomeworkId.value = response.data.id
      committedAction = editingHomeworkId.value ? 'updated' : 'created'
      if (!editingHomeworkId.value) currentPage.value = 1
    }
    if (homeworkAttachment.value) {
      const attachmentData = new FormData()
      attachmentData.append('attachment', homeworkAttachment.value)
      try {
        await api.post(`/homeworks/${pendingHomeworkId.value}/attachment`, attachmentData, { timeout: 60000 })
      } catch (error) {
        await load()
        const prefix = committedAction === 'created'
          ? '作业草稿已创建'
          : committedAction === 'updated' ? '作业草稿已更新' : '作业草稿已保存'
        ElMessage.warning(`${prefix}，但附件上传失败：${error.message || '请检查文件后重试'}`)
        return
      }
    }
    ElMessage.success(editingHomeworkId.value ? '作业草稿已更新' : '作业草稿已创建')
    createDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(error.message || '作业创建失败')
  } finally {
    saving.value = false
  }
}

async function changeStatus(homework, action) {
  const publishing = action === 'publish'
  const prompt = publishing
    ? '发布后将不能再编辑作业内容，确认发布？'
    : '关闭后学生仍可查看成绩，但不能继续提交，确认关闭？'
  try {
    await ElMessageBox.confirm(prompt, publishing ? '发布作业' : '关闭作业', {
      type: publishing ? 'info' : 'warning',
    })
    const response = await api.post(`/homeworks/${homework.id}/${action}`)
    replaceHomework(response.data)
    ElMessage.success(publishing ? '作业已发布' : '作业已关闭')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '作业状态更新失败')
  }
}

async function deleteHomework(homework) {
  try {
    await ElMessageBox.confirm('删除后草稿和已上传附件将无法恢复，确认继续？', '删除作业', {
      type: 'warning',
    })
    await api.delete(`/homeworks/${homework.id}`)
    homeworks.value = homeworks.value.filter((item) => item.id !== homework.id)
    ElMessage.success('作业草稿已删除')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '作业删除失败')
  }
}

function openSubmission(homework) {
  if (saving.value) return
  if (homework.submission?.status === 'GRADED') {
    ElMessage.warning('作业已批改，不能再修改内容或附件')
    return
  }
  selectedHomework.value = homework
  submissionForm.content = homework.submission?.content || ''
  submissionAttachment.value = null
  submissionContentSaved.value = null
  submissionDialog.value = true
}

async function submitHomework() {
  if (saving.value || selectedHomework.value?.submission?.status === 'GRADED') return
  if (!selectedHomeworkOpen.value) {
    ElMessage.warning('作业已截止或关闭，不能继续提交')
    return
  }
  const content = submissionForm.content.trim()
  if (!content && !submissionAttachment.value && !selectedHomework.value?.submission?.attachment) {
    ElMessage.warning('请输入作业内容或选择附件')
    return
  }
  saving.value = true
  const homeworkId = selectedHomework.value.id
  const attachment = submissionAttachment.value
  try {
    let submission = selectedHomework.value.submission
    if (content && content !== submissionContentSaved.value) {
      const response = await api.put(`/homeworks/${homeworkId}/submission`, { content })
      submission = response.data
      submissionContentSaved.value = content
      updateSelectedSubmission(submission)
    }
    if (attachment) {
      const attachmentData = new FormData()
      attachmentData.append('attachment', attachment)
      try {
        const response = await api.post(
          `/homeworks/${homeworkId}/submission/attachment`,
          attachmentData,
        )
        submission = response.data
        updateSelectedSubmission(submission)
      } catch (error) {
        const prefix = submissionContentSaved.value ? '作业内容已保存' : '作业内容未发生变化'
        ElMessage.warning(`${prefix}，但附件上传失败：${error.message || '请检查文件后重试'}`)
        return
      }
    }
    // Upload first when switching to attachment-only, so clearing text never
    // leaves a submission with neither an answer nor an attachment.
    if (!content && submission?.attachment && submission.content) {
      const response = await api.put(`/homeworks/${homeworkId}/submission`, { content: '' })
      submission = response.data
      submissionContentSaved.value = ''
    }
    updateSelectedSubmission(submission)
    submissionDialog.value = false
    ElMessage.success('作业提交成功')
  } catch (error) {
    ElMessage.error(error.message || '作业提交失败')
  } finally {
    saving.value = false
  }
}

async function openSubmissions(homework) {
  if (saving.value) return
  clearGradeContext()
  const requestId = ++submissionsRequestSequence
  selectedHomework.value = homework
  gradeDialog.value = true
  submissionsLoading.value = true
  try {
    const response = await api.get(`/homeworks/${homework.id}/submissions`)
    if (requestId !== submissionsRequestSequence || !gradeDialog.value || selectedHomework.value?.id !== homework.id) return
    submissions.value = response.data
  } catch (error) {
    if (requestId !== submissionsRequestSequence) return
    submissionsError.value = error.message || '学生提交记录加载失败'
    ElMessage.error(error.message || '学生提交记录加载失败')
  } finally {
    if (requestId === submissionsRequestSequence) submissionsLoading.value = false
  }
}

function clearGradeContext() {
  submissionsRequestSequence += 1
  submissionsLoading.value = false
  submissionsError.value = ''
  submissions.value = []
  selectedSubmission.value = null
  Object.assign(gradeForm, { score: 0, teacher_comment: '' })
}

function selectForGrade(submission) {
  if (saving.value) return
  selectedSubmission.value = submission
  gradeForm.score = submission.score ?? 0
  gradeForm.teacher_comment = submission.teacher_comment || ''
}

async function gradeSubmission() {
  if (saving.value || !selectedSubmission.value || !selectedHomework.value) return
  const submission = selectedSubmission.value
  if (!submissions.value.some((item) => item.id === submission.id)
    || (submission.homework_id != null && submission.homework_id !== selectedHomework.value.id)) {
    ElMessage.warning('提交记录已切换，请重新选择学生')
    clearGradeContext()
    return
  }
  const requestId = submissionsRequestSequence
  const payload = { ...gradeForm }
  saving.value = true
  try {
    const response = await api.put(
      `/homeworks/submissions/${submission.id}/grade`,
      payload,
    )
    if (requestId !== submissionsRequestSequence) return
    const index = submissions.value.findIndex((item) => item.id === response.data.id)
    if (index >= 0) submissions.value[index] = response.data
    selectedSubmission.value = null
    ElMessage.success('批改结果已保存')
  } catch (error) {
    ElMessage.error(error.message || '批改失败')
  } finally {
    saving.value = false
  }
}

function replaceHomework(homework) {
  const index = homeworks.value.findIndex((item) => item.id === homework.id)
  if (index >= 0) homeworks.value[index] = homework
}

function updateSelectedSubmission(submission) {
  const homework = { ...selectedHomework.value, submission }
  selectedHomework.value = homework
  replaceHomework(homework)
}

function resetHomeworkForm() {
  pendingHomeworkId.value = null
  editingHomeworkId.value = null
  deadlineMode.value = 'UNLIMITED'
  Object.assign(homeworkForm, {
    course_id: null,
    title: '',
    description: '',
    deadline: null,
    total_score: 100,
  })
  homeworkAttachment.value = null
  homeworkFormRef.value?.clearValidate()
}

function resetSubmissionDialog() {
  submissionContentSaved.value = null
  submissionAttachment.value = null
}

function statusLabel(status) {
  return { DRAFT: '草稿', PUBLISHED: '进行中', CLOSED: '已关闭' }[status] || status
}

function submissionLabel(submission) {
  if (!submission) return '待提交'
  return submission.status === 'GRADED' ? '已批改 · 不可修改' : '已提交'
}

function parseUtc(value) {
  if (!value) return null
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  return new Date(normalized)
}

function formatDate(value) {
  const date = parseUtc(value)
  if (!date || Number.isNaN(date.getTime())) return '长期有效'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function deadlineTone(homework) {
  if (homework.status === 'CLOSED') return 'closed'
  const deadline = parseUtc(homework.deadline)
  if (!deadline) return 'normal'
  return deadline.getTime() <= now.value ? 'overdue' : 'normal'
}

function isHomeworkOpen(homework) {
  return homework.status === 'PUBLISHED'
    && homework.availability !== 'CLOSED'
    && homework.availability !== 'ENDED'
    && homework.can_submit !== false
    && deadlineTone(homework) !== 'overdue'
}

function canEditSubmission(homework) {
  return homework.submission?.status !== 'GRADED' && isHomeworkOpen(homework)
}

function homeworkStateClass(homework) {
  if (homework.status === 'PUBLISHED' && !isHomeworkOpen(homework)) return 'ended'
  return homework.status.toLowerCase()
}

function homeworkStateLabel(homework) {
  return homework.status === 'PUBLISHED' && !isHomeworkOpen(homework) ? '已截止' : statusLabel(homework.status)
}

function homeworkDeadlineLabel(homework) {
  return homework.deadline ? `截止 · ${formatDate(homework.deadline)}` : '长期有效'
}

function openRequirements(homework) {
  requirementsHomework.value = homework
  requirementsDialog.value = true
}

function openTeacherComment(homework) {
  commentHomework.value = homework
  teacherCommentDialog.value = true
}

function selectHomeworkAttachment(event) {
  const file = event.target.files?.[0]
  if (file && (file.size === 0 || file.size > 50 * 1024 * 1024)) {
    ElMessage.warning('请选择非空且不超过 50MB 的附件')
    event.target.value = ''
    return
  }
  homeworkAttachment.value = file || null
}

function selectSubmissionAttachment(event) {
  submissionAttachment.value = event.target.files?.[0] || null
}

async function openAttachment(homework, submission = null) {
  clearPreview()
  const requestId = previewRequestSequence
  previewLoading.value = true
  previewDialog.value = true
  const storedPath = String(submission?.attachment || homework.attachment || '')
  const suffix = storedPath.split('.').pop()?.toLowerCase()
  const label = submission ? `${submission.student_name || '学生'}的提交附件` : `${homework.title} · 教师附件`
  previewName.value = suffix ? `${label}.${suffix}` : label
  const endpoint = submission
    ? `/homeworks/submissions/${submission.id}/attachment`
    : `/homeworks/${homework.id}/attachment`
  try {
    const blob = await api.get(endpoint, { responseType: 'blob', timeout: 30000 })
    if (requestId !== previewRequestSequence || !previewDialog.value) return
    previewUrl.value = URL.createObjectURL(blob)
    const type = String(blob.type || '').toLowerCase()
    previewKind.value = type.startsWith('image/') || ['png', 'jpg', 'jpeg'].includes(suffix)
      ? 'image'
      : type === 'application/pdf' || type.startsWith('text/') || ['pdf', 'txt'].includes(suffix)
        ? 'document'
        : 'unsupported'
  } catch (error) {
    if (requestId !== previewRequestSequence || !previewDialog.value) return
    previewDialog.value = false
    ElMessage.error(error.message || '附件加载失败')
  } finally {
    if (requestId === previewRequestSequence) previewLoading.value = false
  }
}

function downloadPreview() {
  if (!previewUrl.value) return
  const anchor = document.createElement('a')
  anchor.href = previewUrl.value
  anchor.download = previewName.value
  anchor.click()
}

function clearPreview() {
  previewRequestSequence += 1
  previewLoading.value = false
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  previewKind.value = 'unsupported'
}

watch([filterCourse, filterStatus], () => { currentPage.value = 1 })
watch(() => filteredHomeworks.value.length, (total) => {
  currentPage.value = Math.min(currentPage.value, Math.max(1, Math.ceil(total / pageSize)))
})
onMounted(() => {
  void load()
  deadlineTicker = window.setInterval(() => { now.value = Date.now() }, 1000)
})
onBeforeUnmount(() => { window.clearInterval(deadlineTicker); clearPreview(); clearGradeContext() })
</script>

<template>
  <section class="page-section homework-center" v-loading="loading">
    <div class="page-heading">
      <div>
        <p class="eyebrow">课程作业</p>
        <h1>{{ isTeacher ? '作业管理' : '课程作业' }}</h1>
        <p>{{ isTeacher ? '发布课程任务，集中查看提交并完成批改。' : '按时完成课程任务，随时查看成绩与教师评语。' }}</p>
      </div>
      <el-button v-if="isTeacher" type="primary" size="large" @click="openHomework()">
        ＋ 创建作业
      </el-button>
    </div>

    <el-result v-if="loadError" icon="error" title="作业列表加载失败" :sub-title="loadError">
      <template #extra><el-button @click="load">重新加载</el-button></template>
    </el-result>
    <template v-else>
    <div class="course-filter-panel task-filter-panel" aria-label="作业筛选条件">
      <div class="course-filter-field">
        <span>所属课程</span>
        <el-select v-model="filterCourse" clearable placeholder="全部课程" aria-label="作业所属课程" popper-class="course-filter-dropdown">
          <el-option v-for="item in homeworkCourseOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </div>
      <div class="course-filter-field">
        <span>作业状态</span>
        <el-select v-model="filterStatus" clearable placeholder="全部状态" aria-label="作业状态" popper-class="course-filter-dropdown">
          <el-option label="进行中" value="OPEN" />
          <el-option label="已截止" value="ENDED" />
          <el-option label="已关闭" value="CLOSED" />
          <el-option v-if="isTeacher" label="草稿" value="DRAFT" />
        </el-select>
      </div>
      <div class="course-filter-field course-keyword-field">
        <span>作业关键词</span>
        <el-input v-model="keywordInput" clearable maxlength="100" placeholder="搜索作业名称、要求或课程" aria-label="作业关键词" @clear="applyFilters" @keyup.enter="applyFilters" />
      </div>
      <div class="course-filter-actions">
        <el-button type="primary" @click="applyFilters">查询</el-button>
        <el-button :disabled="!hasActiveFilters && !keywordInput" @click="resetFilters">重置</el-button>
      </div>
    </div>
    <div class="course-result-meta">
      <span>{{ hasActiveFilters ? `当前条件下共 ${filteredHomeworks.length} 项作业` : `共 ${filteredHomeworks.length} 项作业` }}</span><i></i>
    </div>
    <div class="homework-summary">
      <article>
        <span>{{ isTeacher ? '全部作业' : '课程任务' }}</span>
        <strong>{{ filteredHomeworks.length }}</strong>
      </article>
      <article>
        <span>{{ isTeacher ? '进行中' : '待完成' }}</span>
        <strong>{{ filteredHomeworks.filter((item) => isHomeworkOpen(item) && (isTeacher || !item.submission)).length }}</strong>
      </article>
      <article>
        <span>{{ isTeacher ? '已结束' : '已批改' }}</span>
        <strong>{{ filteredHomeworks.filter((item) => isTeacher ? !isHomeworkOpen(item) && item.status !== 'DRAFT' : item.submission?.status === 'GRADED').length }}</strong>
      </article>
    </div>

    <div
      class="stable-pagination-shell homework-pagination-shell"
      :class="{ 'has-pagination': filteredHomeworks.length > pageSize }"
    >
    <div class="homework-grid stable-pagination-body">
      <article v-for="homework in pagedHomeworks" :key="homework.id" class="homework-card">
        <div class="homework-card-top">
          <span>{{ homework.course_name }}</span>
          <i :class="`homework-state state-${homeworkStateClass(homework)}`">
            {{ homeworkStateLabel(homework) }}
          </i>
        </div>
        <h2>{{ homework.title }}</h2>
        <p>{{ homework.description }}</p>
        <el-button class="homework-requirement-button" link @click="openRequirements(homework)">查看完整要求</el-button>
        <div class="homework-meta">
          <span :class="deadlineTone(homework)">{{ homeworkDeadlineLabel(homework) }}</span>
          <span>满分 · {{ homework.total_score }}</span>
        </div>
        <div
          v-if="homework.attachment || (!isTeacher && homework.submission?.attachment)"
          class="homework-attachment-row"
        >
          <button
            v-if="homework.attachment"
            class="homework-attachment"
            type="button"
            @click="openAttachment(homework)"
          >在线预览教师附件</button>
          <button
            v-if="!isTeacher && homework.submission?.attachment"
            type="button"
            class="attachment-text-button student-submission-attachment"
            @click="openAttachment(homework, homework.submission)"
          >在线预览我的提交附件</button>
        </div>

        <div v-if="!isTeacher" class="submission-result">
          <div class="submission-result-summary">
            <span>{{ submissionLabel(homework.submission) }}</span>
            <div class="submission-result-actions">
              <button
                v-if="homework.submission?.teacher_comment"
                type="button"
                class="teacher-comment-button"
                @click="openTeacherComment(homework)"
              >查看教师评语</button>
              <strong v-if="homework.submission?.score !== null && homework.submission?.score !== undefined">
                {{ homework.submission.score }} 分
              </strong>
              <button
                v-if="canEditSubmission(homework)"
                type="button"
                class="submission-action-button"
                @click="openSubmission(homework)"
              >{{ homework.submission ? '修改提交' : '提交作业' }}</button>
            </div>
          </div>
        </div>

        <div v-if="isTeacher" class="homework-actions">
          <template v-if="isTeacher">
            <el-button
              v-if="homework.status === 'DRAFT'"
              plain
              @click="openHomework(homework)"
            >编辑</el-button>
            <el-button
              v-if="homework.status === 'DRAFT'"
              type="primary"
              @click="changeStatus(homework, 'publish')"
            >
              发布
            </el-button>
            <el-button
              v-if="homework.status === 'DRAFT'"
              type="danger"
              plain
              @click="deleteHomework(homework)"
            >
              删除
            </el-button>
            <el-button
              v-if="homework.status === 'PUBLISHED'"
              type="warning"
              plain
              @click="changeStatus(homework, 'close')"
            >
              关闭
            </el-button>
            <el-button v-if="homework.status !== 'DRAFT'" @click="openSubmissions(homework)">
              查看提交（{{ homework.submission_count }}）
            </el-button>
          </template>
        </div>
      </article>
      <el-empty
        v-if="!loading && !filteredHomeworks.length"
        class="surface-card homework-empty"
        :description="hasActiveFilters ? '没有符合当前筛选条件的作业' : isTeacher ? '还没有作业，先创建一份草稿吧' : '当前没有需要完成的课程作业'"
      />
    </div>
      <el-pagination
        v-if="filteredHomeworks.length > pageSize"
        v-model:current-page="currentPage"
        class="collection-pagination"
        background
        layout="prev, pager, next"
        :page-size="pageSize"
        :total="filteredHomeworks.length"
        aria-label="作业列表分页"
      />
    </div>
    </template>

    <el-dialog v-model="requirementsDialog" :title="`${requirementsHomework?.title || ''} · 作业要求`" width="min(680px, 94vw)" @close-auto-focus="restoreRequirementsFocus">
      <p class="task-full-description">{{ requirementsHomework?.description }}</p>
      <template #footer><el-button @click="requirementsDialog = false">关闭</el-button></template>
    </el-dialog>

    <el-dialog
      v-model="teacherCommentDialog"
      :title="`${commentHomework?.title || ''} · 教师评语`"
      width="min(560px, 94vw)"
      @close-auto-focus="restoreTeacherCommentFocus"
      @closed="commentHomework = null"
    >
      <div class="teacher-comment-content">
        {{ commentHomework?.submission?.teacher_comment || '教师暂未填写评语。' }}
      </div>
      <template #footer><el-button @click="teacherCommentDialog = false">关闭</el-button></template>
    </el-dialog>

    <el-dialog
      v-model="createDialog"
      @close-auto-focus="restoreCreateFocus"
      :title="editingHomeworkId ? '编辑作业草稿' : '创建作业草稿'"
      width="min(620px, 94vw)"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      @closed="resetHomeworkForm"
    >
      <p v-if="pendingHomeworkId" class="dialog-tip">
        草稿已经保存，课程与作业内容已锁定；请重新选择附件并重试，不会重复创建草稿。
      </p>
      <el-form
        ref="homeworkFormRef"
        :model="homeworkForm"
        :rules="homeworkRules"
        :disabled="saving || Boolean(pendingHomeworkId)"
        label-position="top"
      >
        <el-form-item label="所属课程" prop="course_id">
          <el-select v-model="homeworkForm.course_id" placeholder="请选择课程" style="width: 100%">
            <el-option
              v-for="course in courses"
              :key="course.id"
              :label="`${course.name}（${course.status === 'PUBLISHED' ? '已发布' : '草稿'}）`"
              :value="course.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="作业标题" prop="title">
          <el-input v-model.trim="homeworkForm.title" maxlength="200" show-word-limit placeholder="例如：第一章知识总结" />
        </el-form-item>
        <el-form-item label="作业要求" prop="description">
          <el-input
            v-model.trim="homeworkForm.description"
            type="textarea"
            :rows="5"
            maxlength="10000"
            show-word-limit
            placeholder="说明完成要求、提交格式与评分要点…"
          />
        </el-form-item>
        <el-form-item label="提交期限">
          <el-radio-group v-model="deadlineMode" aria-label="作业提交期限">
            <el-radio-button value="UNLIMITED">不限时</el-radio-button>
            <el-radio-button value="LIMITED">指定截止时间</el-radio-button>
          </el-radio-group>
          <small class="field-help">不限时作业发布后会一直开放，直到教师手动关闭。</small>
        </el-form-item>
        <div class="homework-form-row" :class="{ 'single-column': deadlineMode === 'UNLIMITED' }">
          <el-form-item v-if="deadlineMode === 'LIMITED'" label="截止时间" required>
            <el-date-picker
              v-model="homeworkForm.deadline"
              type="datetime"
              placeholder="请选择截止时间"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item label="作业满分">
            <el-input-number v-model="homeworkForm.total_score" :min="0.01" :max="999.99" :precision="2" />
          </el-form-item>
        </div>
        <el-form-item label="作业附件（可选）">
          <el-button v-if="existingTeacherAttachment" :disabled="false" @click="openAttachment(existingTeacherAttachment)">查看现有附件</el-button>
          <label class="file-picker compact-file-picker">
            <input type="file" :disabled="saving" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.zip,.rar,.7z,.jpg,.jpeg,.png" @change="selectHomeworkAttachment" />
            <span>{{ existingTeacherAttachment ? '替换附件' : '选择附件' }}</span>
            <strong>{{ homeworkAttachment?.name || '最大 50MB' }}</strong>
          </label>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="createDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveHomework">
          {{ pendingHomeworkId ? '重试上传附件' : editingHomeworkId ? '保存修改' : '保存草稿' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="submissionDialog"
      @close-auto-focus="restoreSubmissionFocus"
      :title="selectedHomework?.title"
      width="min(640px, 94vw)"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      @closed="resetSubmissionDialog"
    >
      <p class="dialog-tip" :class="{ 'deadline-ended-tip': !selectedHomeworkOpen }">
        {{ selectedHomeworkOpen
          ? '在作业开放且未截止、未批改时可以修改提交；教师批改后，内容和附件均不可再修改。'
          : '作业已截止或关闭，当前内容仅供查看，不能继续提交。' }}
      </p>
      <details class="task-requirements">
        <summary>查看完整作业要求</summary>
        <p class="task-full-description">{{ selectedHomework?.description }}</p>
      </details>
      <el-input
        v-model="submissionForm.content"
        type="textarea"
        :rows="9"
        :disabled="saving || !selectedHomeworkOpen"
        maxlength="20000"
        show-word-limit
        placeholder="请输入作业答案或总结…"
      />
      <label class="file-picker compact-file-picker submission-file-picker">
        <input type="file" :disabled="saving || !selectedHomeworkOpen" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.zip,.rar,.7z,.jpg,.jpeg,.png" @change="selectSubmissionAttachment" />
        <span>选择提交附件</span>
        <strong>{{ submissionAttachment?.name || '可只提交附件，最大 50MB' }}</strong>
      </label>
      <template #footer>
        <el-button :disabled="saving" @click="submissionDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" :disabled="!selectedHomeworkOpen" @click="submitHomework">
          {{ selectedHomeworkOpen ? '确认提交' : '已截止' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="gradeDialog" :title="`${selectedHomework?.title || ''} · 提交记录`" width="min(900px, 96vw)" :close-on-click-modal="!saving" :close-on-press-escape="!saving" :show-close="!saving" @close="clearGradeContext" @close-auto-focus="restoreGradeFocus">
      <div v-loading="submissionsLoading">
      <el-result v-if="submissionsError" icon="error" title="提交记录加载失败" :sub-title="submissionsError">
        <template #extra><el-button @click="openSubmissions(selectedHomework)">重新加载</el-button></template>
      </el-result>
      <el-table v-else :data="submissions" max-height="360">
        <el-table-column prop="student_name" label="学生" width="130"><template #default="scope"><OverflowText :text="scope.row.student_name" label="查看学生姓名全文" /></template></el-table-column>
        <el-table-column prop="content" label="提交内容" min-width="260"><template #default="scope"><OverflowText :text="scope.row.content" label="查看提交内容全文" /></template></el-table-column>
        <el-table-column label="提交时间" width="150">
          <template #default="scope">{{ formatDate(scope.row.submit_time) }}</template>
        </el-table-column>
        <el-table-column label="成绩" width="100">
          <template #default="scope">{{ scope.row.score ?? '待批改' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="155">
          <template #default="scope">
            <el-button v-if="scope.row.attachment" link @click="openAttachment(selectedHomework, scope.row)">预览附件</el-button>
            <el-button link type="primary" :disabled="saving" @click="selectForGrade(scope.row)">批改</el-button>
          </template>
        </el-table-column>
        <template #empty><el-empty description="还没有学生提交" :image-size="64" /></template>
      </el-table>
      </div>
      <div v-if="selectedSubmission" class="grade-panel">
        <div>
          <strong>正在批改：{{ selectedSubmission.student_name }}</strong>
          <span>满分 {{ selectedHomework.total_score }}</span>
        </div>
        <p>{{ selectedSubmission.content }}</p>
        <div class="grade-form-row">
          <el-input-number
            :disabled="saving"
            v-model="gradeForm.score"
            :min="0"
            :max="selectedHomework.total_score"
            :precision="2"
          />
          <el-input v-model="gradeForm.teacher_comment" :disabled="saving" maxlength="10000" placeholder="填写教师评语（可选）" />
          <el-button type="primary" :loading="saving" @click="gradeSubmission">保存批改</el-button>
        </div>
      </div>
    </el-dialog>
    <el-dialog v-model="previewDialog" :title="previewName" width="min(920px, 96vw)" @close="clearPreview" @close-auto-focus="restorePreviewFocus">
      <div v-loading="previewLoading" class="attachment-preview">
        <img v-if="previewUrl && previewKind === 'image'" :src="previewUrl" :alt="previewName" />
        <iframe v-else-if="previewUrl && previewKind === 'document'" :src="previewUrl" :title="previewName"></iframe>
        <el-empty v-else-if="!previewLoading" description="该格式无法在浏览器内直接预览，请下载后使用本机软件打开" :image-size="64" />
      </div>
      <template #footer><el-button :disabled="!previewUrl" @click="downloadPreview">下载附件</el-button><el-button @click="previewDialog = false">关闭</el-button></template>
    </el-dialog>
  </section>
</template>
