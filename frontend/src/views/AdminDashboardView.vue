<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import api from '../api/client'


const activeSection = ref('videos')
const loading = ref(false)
const refreshingVideos = ref(false)
const saving = ref(false)
const overview = ref({})
const videoOperations = ref({ items: [], summary: {}, runtime: {} })
const users = ref([])
const courses = ref([])
const classrooms = ref([])
const categories = ref([])
const notices = ref([])
const userDialog = ref(false)
const noticeDialog = ref(false)
const categoryDialog = ref(false)
const userFormRef = ref(null)
const editingNoticeId = ref(null)
const editingCategoryId = ref(null)
const userFilters = reactive({ role: '', status: '', keyword: '' })
const videoFilters = reactive({ status: '', keyword: '' })
const courseFilters = reactive({ status: '', keyword: '' })
const classKeyword = ref('')
const userForm = reactive({
  role: 'STUDENT', username: '', password: '', real_name: '',
  student_no: '', teacher_no: '', email: '', phone: '',
})
const noticeForm = reactive({ title: '', content: '' })
const categoryForm = reactive({ name: '', description: '', sort_order: 0 })
let userSearchSequence = 0
let videoSearchSequence = 0
let videoPoller = null

const userRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9_\u4e00-\u9fff]{3,50}$/, message: '用户名需为 3–50 位中文、字母、数字或下划线', trigger: 'blur' },
  ],
  real_name: [
    { required: true, message: '请输入真实姓名', trigger: 'blur' },
    { max: 50, message: '真实姓名不能超过 50 位', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入初始密码', trigger: 'blur' },
    { min: 8, max: 72, message: '密码长度需为 8–72 位', trigger: 'blur' },
  ],
  student_no: [
    { required: true, message: '请输入学号', trigger: 'blur' },
    { max: 50, message: '学号不能超过 50 位', trigger: 'blur' },
  ],
  teacher_no: [
    { required: true, message: '请输入工号', trigger: 'blur' },
    { max: 50, message: '工号不能超过 50 位', trigger: 'blur' },
  ],
  email: [
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
    { max: 100, message: '邮箱不能超过 100 位', trigger: 'blur' },
  ],
  phone: [{ pattern: /^1[3-9]\d{9}$/, message: '请输入正确的 11 位手机号', trigger: 'blur' }],
}

const processingVideoCount = computed(() => (
  (videoOperations.value.summary?.PENDING || 0)
  + (videoOperations.value.summary?.PROCESSING || 0)
  + (videoOperations.value.summary?.UPLOADING || 0)
))

const videoSummaryItems = computed(() => [
  { label: '全部', key: 'all', value: videoOperations.value.summary?.total || 0 },
  { label: '等待', key: 'pending', value: (videoOperations.value.summary?.UPLOADING || 0) + (videoOperations.value.summary?.PENDING || 0) },
  { label: '处理中', key: 'processing', value: videoOperations.value.summary?.PROCESSING || 0 },
  { label: '可播放', key: 'ready', value: videoOperations.value.summary?.READY || 0 },
  { label: '失败', key: 'failed', value: videoOperations.value.summary?.FAILED || 0 },
])

const sections = computed(() => [
  { value: 'videos', label: '视频处理', count: videoOperations.value.summary?.total || 0 },
  { value: 'users', label: '用户账号', count: overview.value.users || 0 },
  { value: 'resources', label: '课程与班级', count: courses.value.length + classrooms.value.length },
  { value: 'categories', label: '课程分类', count: categories.value.length },
  { value: 'notices', label: '系统公告', count: notices.value.length },
])

const metrics = computed(() => [
  { label: '系统用户', value: overview.value.users || 0, detail: `活跃 ${overview.value.active_users || 0}` },
  { label: '课程总数', value: overview.value.courses || 0, detail: `已发布 ${overview.value.published_courses || 0}` },
  { label: '视频任务', value: videoOperations.value.summary?.total || 0, detail: `待处理 ${processingVideoCount.value} · 失败 ${videoOperations.value.summary?.FAILED || 0}` },
  { label: '教学班级', value: classrooms.value.length, detail: '跨教师统一监管' },
  { label: '学习记录', value: overview.value.learning_records || 0, detail: '实时累计' },
  { label: '作业 / 测验提交', value: `${overview.value.homework_submissions || 0} / ${overview.value.exam_records || 0}`, detail: '业务记录' },
])

const runtimeHealthy = computed(() => (
  videoOperations.value.runtime?.ffmpeg?.available
  && videoOperations.value.runtime?.ffprobe?.available
))

function compactParams(filters) {
  return Object.fromEntries(
    Object.entries(filters)
      .map(([key, value]) => [key, typeof value === 'string' ? value.trim() : value])
      .filter(([, value]) => value !== '' && value !== null && value !== undefined),
  )
}

async function loadOverview() {
  overview.value = (await api.get('/statistics')).data
}

async function loadVideos({ quiet = false } = {}) {
  const requestId = ++videoSearchSequence
  if (!quiet) refreshingVideos.value = true
  try {
    const response = await api.get('/admin/videos', { params: compactParams(videoFilters) })
    if (requestId === videoSearchSequence) videoOperations.value = response.data
  } catch (error) {
    if (!quiet && requestId === videoSearchSequence) ElMessage.error(error.message || '视频任务加载失败')
  } finally {
    if (!quiet && requestId === videoSearchSequence) refreshingVideos.value = false
  }
}

async function loadUsers() {
  const requestId = ++userSearchSequence
  const response = await api.get('/admin/users', { params: compactParams(userFilters) })
  if (requestId === userSearchSequence) users.value = response.data
}

async function searchUsers() {
  try { await loadUsers() } catch (error) { ElMessage.error(error.message || '用户查询失败') }
}

async function loadCourses() {
  try {
    courses.value = (await api.get('/admin/courses', { params: compactParams(courseFilters) })).data
  } catch (error) { ElMessage.error(error.message || '课程查询失败') }
}

async function loadClasses() {
  try {
    classrooms.value = (await api.get('/admin/classes', { params: compactParams({ keyword: classKeyword.value }) })).data
  } catch (error) { ElMessage.error(error.message || '班级查询失败') }
}

async function loadCategories() {
  categories.value = (await api.get('/admin/categories')).data
}

async function loadNotices() {
  notices.value = (await api.get('/notices/manage')).data
}

async function load() {
  loading.value = true
  const results = await Promise.allSettled([
    loadOverview(), loadVideos({ quiet: true }), loadUsers(), loadCourses(),
    loadClasses(), loadCategories(), loadNotices(),
  ])
  loading.value = false
  if (results.some((item) => item.status === 'rejected')) {
    ElMessage.error('部分后台数据加载失败，请使用对应区域的刷新或查询按钮重试')
  }
}

async function retryVideo(video) {
  try {
    await ElMessageBox.confirm(
      `确认重新处理“${video.title}”？系统会清理未完成的转码产物，并从原始文件重新开始。`,
      '重新转码',
      { type: 'warning' },
    )
    const response = await api.post(`/admin/videos/${video.id}/retry`, null, { timeout: 0 })
    ElMessage.success(response.message || '视频已重新加入转码流程')
    await Promise.all([loadVideos(), loadOverview()])
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '视频重新转码失败')
  }
}

async function removeVideo(video) {
  try {
    await ElMessageBox.confirm(
      `将永久删除“${video.title}”的失败任务、原始文件和残留产物，此操作不可恢复。`,
      '清理失败任务',
      { type: 'error', confirmButtonText: '确认清理' },
    )
    await api.delete(`/admin/videos/${video.id}`)
    ElMessage.success('失败任务及相关文件已清理')
    await Promise.all([loadVideos(), loadOverview()])
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '任务清理失败')
  }
}

async function createUser() {
  const valid = await userFormRef.value?.validate().catch(() => false)
  if (!valid || saving.value) return
  saving.value = true
  try {
    const payload = {
      role: userForm.role,
      username: userForm.username.trim(),
      password: userForm.password,
      real_name: userForm.real_name.trim(),
      email: userForm.email.trim() || null,
      phone: userForm.phone.trim() || null,
      ...(userForm.role === 'STUDENT'
        ? { student_no: userForm.student_no.trim() }
        : { teacher_no: userForm.teacher_no.trim() }),
    }
    await api.post('/admin/users', payload)
    userDialog.value = false
    resetUserForm()
    ElMessage.success('用户账号已创建')
    await Promise.all([loadUsers(), loadOverview()])
  } catch (error) {
    ElMessage.error(error.message || '用户创建失败')
  } finally { saving.value = false }
}

async function toggleUser(user) {
  const nextStatus = !user.status
  try {
    await ElMessageBox.confirm(
      nextStatus ? '确认启用该用户账号？' : '禁用后该用户将无法继续访问受保护功能，确认继续？',
      nextStatus ? '启用用户' : '禁用用户',
      { type: nextStatus ? 'info' : 'warning' },
    )
    const response = await api.put(`/admin/users/${user.id}/status`, { status: nextStatus })
    const index = users.value.findIndex((item) => item.id === user.id)
    if (index >= 0) users.value[index] = response.data
    ElMessage.success(nextStatus ? '用户已启用' : '用户已禁用')
    await loadOverview()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '用户状态更新失败')
  }
}

async function changeCourseStatus(course, status) {
  try {
    await ElMessageBox.confirm(
      status === 'OFFLINE'
        ? `下线“${course.name}”后学生将无法继续进入课程，确认继续？`
        : `确认恢复发布“${course.name}”？`,
      status === 'OFFLINE' ? '强制下线' : '恢复发布',
      { type: status === 'OFFLINE' ? 'warning' : 'info' },
    )
    await api.put(`/admin/courses/${course.id}/status`, { status })
    ElMessage.success(`课程已${status === 'OFFLINE' ? '下线' : '发布'}`)
    await Promise.all([loadCourses(), loadOverview()])
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '课程状态更新失败')
  }
}

async function removeClassroom(classroom) {
  try {
    await ElMessageBox.confirm(
      `删除“${classroom.name}”会同时解除 ${classroom.member_count} 条班级成员关系，但不会删除学生账号。`,
      '删除班级',
      { type: 'error', confirmButtonText: '确认删除' },
    )
    await api.delete(`/admin/classes/${classroom.id}`)
    ElMessage.success('班级及成员关系已删除')
    await loadClasses()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '班级删除失败')
  }
}

function openCategory(category = null) {
  editingCategoryId.value = category?.id || null
  Object.assign(categoryForm, {
    name: category?.name || '', description: category?.description || '', sort_order: category?.sort_order || 0,
  })
  categoryDialog.value = true
}

async function saveCategory() {
  if (!categoryForm.name.trim()) { ElMessage.warning('请填写分类名称'); return }
  saving.value = true
  try {
    const payload = {
      name: categoryForm.name.trim(),
      description: categoryForm.description.trim() || null,
      sort_order: categoryForm.sort_order,
    }
    if (editingCategoryId.value) {
      await api.put(`/admin/categories/${editingCategoryId.value}`, payload)
      ElMessage.success('课程分类已更新')
    } else {
      await api.post('/admin/categories', payload)
      ElMessage.success('课程分类已创建')
    }
    categoryDialog.value = false
    await loadCategories()
  } catch (error) {
    ElMessage.error(error.message || '课程分类保存失败')
  } finally { saving.value = false }
}

async function toggleCategory(category) {
  const nextStatus = !category.status
  try {
    await ElMessageBox.confirm(
      nextStatus ? `确认启用“${category.name}”？` : `禁用“${category.name}”后教师将不能用它创建或修改课程，已有课程不受影响。`,
      nextStatus ? '启用分类' : '禁用分类',
      { type: nextStatus ? 'info' : 'warning' },
    )
    await api.put(`/admin/categories/${category.id}/status`, { status: nextStatus })
    ElMessage.success(nextStatus ? '分类已启用' : '分类已禁用')
    await loadCategories()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '分类状态更新失败')
  }
}

function openNotice(notice = null) {
  editingNoticeId.value = notice?.id || null
  noticeForm.title = notice?.title || ''
  noticeForm.content = notice?.content || ''
  noticeDialog.value = true
}

async function saveNotice() {
  if (!noticeForm.title.trim() || !noticeForm.content.trim()) { ElMessage.warning('请填写公告标题和内容'); return }
  saving.value = true
  try {
    if (editingNoticeId.value) {
      await api.put(`/notices/${editingNoticeId.value}`, noticeForm)
      ElMessage.success('公告已更新')
    } else {
      await api.post('/notices', noticeForm)
      ElMessage.success('公告草稿已创建')
    }
    noticeDialog.value = false
    await loadNotices()
  } catch (error) {
    ElMessage.error(error.message || '公告保存失败')
  } finally { saving.value = false }
}

async function changeNoticeStatus(notice, status) {
  try {
    await api.put(`/notices/${notice.id}/status`, { status })
    ElMessage.success(status === 'PUBLISHED' ? '公告已发布' : '公告已下线')
    await loadNotices()
  } catch (error) { ElMessage.error(error.message || '公告状态更新失败') }
}

async function removeNotice(notice) {
  try {
    await ElMessageBox.confirm('确认删除这份公告？', '删除公告', { type: 'warning' })
    await api.delete(`/notices/${notice.id}`)
    notices.value = notices.value.filter((item) => item.id !== notice.id)
    ElMessage.success('公告已删除')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '公告删除失败')
  }
}

function resetUserForm() {
  Object.assign(userForm, {
    role: 'STUDENT', username: '', password: '', real_name: '',
    student_no: '', teacher_no: '', email: '', phone: '',
  })
  nextTick(() => userFormRef.value?.clearValidate())
}

watch(() => userForm.role, (role) => {
  if (role === 'STUDENT') userForm.teacher_no = ''
  if (role === 'TEACHER') userForm.student_no = ''
  userFormRef.value?.clearValidate(['student_no', 'teacher_no'])
})

function roleLabel(role) { return { ADMIN: '管理员', TEACHER: '教师', STUDENT: '学生' }[role] || role }
function courseStatusLabel(status) { return { DRAFT: '草稿', PUBLISHED: '已发布', OFFLINE: '已下线' }[status] || status }
function videoStatusLabel(status) { return { UPLOADING: '上传中', PENDING: '等待处理', PROCESSING: '处理中', READY: '可播放', FAILED: '失败' }[status] || status }
function videoStepLabel(step) {
  return { QUEUED: '等待队列', PROBING: '读取媒体信息', TRANSCODING: '生成标准 MP4', HLS: '生成 HLS 分片', COVER: '提取封面', FINISHED: '处理完成' }[step] || (step || '等待处理')
}
function noticeStatusLabel(status) { return { DRAFT: '草稿', PUBLISHED: '已发布', OFFLINE: '已下线' }[status] || status }

function formatDate(value) {
  if (!value) return '—'
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(normalized))
}

function formatBytes(value) {
  if (!Number.isFinite(Number(value))) return '—'
  const bytes = Number(value)
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

function formatMedia(video) {
  const resolution = video.width && video.height ? `${video.width}×${video.height}` : '分辨率未知'
  const codec = [video.video_codec, video.audio_codec].filter(Boolean).join(' / ') || '编码未知'
  return `${resolution} · ${codec}`
}

onMounted(() => {
  load()
  videoPoller = window.setInterval(() => {
    if (activeSection.value === 'videos' && processingVideoCount.value > 0) loadVideos({ quiet: true })
  }, 8000)
})
onBeforeUnmount(() => window.clearInterval(videoPoller))
</script>

<template>
  <section class="page-section admin-dashboard" v-loading="loading">
    <div class="page-heading">
      <div><p class="eyebrow">系统管理</p><h1>系统后台</h1><p>集中处理转码异常、账号权限、课程资源、教学班级和系统公告。</p></div>
    </div>

    <div class="admin-metrics">
      <article v-for="metric in metrics" :key="metric.label"><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong><small>{{ metric.detail }}</small></article>
    </div>

    <nav class="admin-section-tabs" aria-label="后台管理功能">
      <button v-for="section in sections" :key="section.value" type="button" :class="{ active: activeSection === section.value }" @click="activeSection = section.value">
        {{ section.label }}<span>{{ section.count }}</span>
      </button>
    </nav>

    <div v-if="activeSection === 'videos'" class="management-surface admin-panel admin-video-center">
      <div class="surface-heading admin-panel-heading">
        <div><strong>视频处理中心</strong><span>查看每一步转码状态，恢复异常任务并清理失败文件</span></div>
        <el-button :loading="refreshingVideos" @click="loadVideos()">刷新状态</el-button>
      </div>
      <div class="video-runtime-bar">
        <div><span :class="['runtime-dot', runtimeHealthy ? 'healthy' : 'unhealthy']" /><strong>{{ runtimeHealthy ? '媒体工具可用' : '媒体工具异常' }}</strong></div>
        <span>FFmpeg：{{ videoOperations.runtime?.ffmpeg?.available ? '可用' : '不可用' }}</span>
        <span>FFprobe：{{ videoOperations.runtime?.ffprobe?.available ? '可用' : '不可用' }}</span>
        <span>处理模式：{{ videoOperations.runtime?.mode === 'ASYNC' ? '异步队列' : '同步处理' }}</span>
        <small>处理中或等待任务超过 {{ videoOperations.runtime?.stale_after_minutes || 30 }} 分钟未更新后可人工恢复</small>
      </div>
      <div class="video-summary-grid">
        <article v-for="item in videoSummaryItems" :key="item.key">
          <span>{{ item.label }}</span><strong :class="`state-${item.key}`">{{ item.value }}</strong>
        </article>
      </div>
      <div class="admin-filters video-filters">
        <el-input v-model="videoFilters.keyword" clearable placeholder="搜索视频、课程、教师或文件名" @keyup.enter="loadVideos()" />
        <el-select v-model="videoFilters.status" placeholder="全部状态">
          <el-option label="全部状态" value="" /><el-option label="上传中" value="UPLOADING" /><el-option label="等待处理" value="PENDING" /><el-option label="处理中" value="PROCESSING" /><el-option label="可播放" value="READY" /><el-option label="失败" value="FAILED" />
        </el-select>
        <el-button type="primary" @click="loadVideos()">查询任务</el-button>
      </div>
      <p class="table-scroll-hint">左右滑动表格可查看媒体参数、错误原因和操作</p>
      <el-table :data="videoOperations.items" max-height="530" empty-text="没有符合条件的视频任务">
        <el-table-column label="视频 / 文件" min-width="220" fixed="left">
          <template #default="scope"><div class="admin-primary-cell"><strong>{{ scope.row.title }}</strong><span>{{ scope.row.original_name || '未记录原文件名' }} · {{ formatBytes(scope.row.file_size) }}</span></div></template>
        </el-table-column>
        <el-table-column label="课程位置" min-width="190">
          <template #default="scope"><div class="admin-primary-cell"><strong>{{ scope.row.course_name }}</strong><span>{{ scope.row.chapter_title }} · {{ scope.row.teacher_name }}</span></div></template>
        </el-table-column>
        <el-table-column label="状态" width="110"><template #default="scope"><span :class="['operation-state', `state-${scope.row.status.toLowerCase()}`]">{{ videoStatusLabel(scope.row.status) }}</span></template></el-table-column>
        <el-table-column label="处理阶段 / 错误" min-width="230">
          <template #default="scope"><div class="video-step-cell"><strong>{{ videoStepLabel(scope.row.process_step) }}</strong><span v-if="scope.row.status === 'FAILED'" class="video-error">{{ scope.row.error_message || '未记录错误原因' }}</span><span v-else>{{ formatMedia(scope.row) }}</span></div></template>
        </el-table-column>
        <el-table-column label="原始文件" width="105"><template #default="scope"><span :class="['file-presence', scope.row.original_exists ? 'present' : 'missing']">{{ scope.row.original_exists ? '文件存在' : '文件丢失' }}</span></template></el-table-column>
        <el-table-column label="最后更新" width="130"><template #default="scope">{{ formatDate(scope.row.updated_at) }}</template></el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="scope"><el-button v-if="scope.row.retryable" link type="primary" @click="retryVideo(scope.row)">重新转码</el-button><el-button v-if="scope.row.removable" link type="danger" @click="removeVideo(scope.row)">清理</el-button><span v-if="!scope.row.retryable && !scope.row.removable" class="no-action">无需处理</span></template>
        </el-table-column>
      </el-table>
    </div>

    <div v-else-if="activeSection === 'users'" class="management-surface admin-panel admin-users">
      <div class="surface-heading admin-panel-heading"><div><strong>用户账号管理</strong><span>{{ users.length }} 条结果</span></div><el-button type="primary" @click="userDialog = true">＋ 创建用户</el-button></div>
      <div class="admin-filters">
        <el-input v-model="userFilters.keyword" clearable placeholder="搜索用户名、姓名、学号或工号" @keyup.enter="searchUsers" />
        <el-select v-model="userFilters.role" placeholder="全部角色"><el-option label="全部角色" value="" /><el-option label="学生" value="STUDENT" /><el-option label="教师" value="TEACHER" /><el-option label="管理员" value="ADMIN" /></el-select>
        <el-select v-model="userFilters.status" placeholder="全部状态"><el-option label="全部状态" value="" /><el-option label="正常" value="true" /><el-option label="已禁用" value="false" /></el-select>
        <el-button type="primary" @click="searchUsers">查询用户</el-button>
      </div>
      <p class="table-scroll-hint">左右滑动表格可查看账号状态和操作</p>
      <el-table :data="users" max-height="530">
        <el-table-column prop="username" label="用户名" min-width="140" /><el-table-column prop="real_name" label="姓名" min-width="120" />
        <el-table-column label="角色" width="100"><template #default="scope">{{ roleLabel(scope.row.role) }}</template></el-table-column>
        <el-table-column label="学号 / 工号" min-width="150"><template #default="scope">{{ scope.row.student_no || scope.row.teacher_no || '—' }}</template></el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="190"><template #default="scope">{{ scope.row.email || '—' }}</template></el-table-column>
        <el-table-column label="状态" width="90"><template #default="scope"><span :class="['account-state', scope.row.status ? 'active' : 'disabled']">{{ scope.row.status ? '正常' : '禁用' }}</span></template></el-table-column>
        <el-table-column label="操作" width="100" fixed="right"><template #default="scope"><el-button v-if="scope.row.role !== 'ADMIN'" link :type="scope.row.status ? 'danger' : 'primary'" @click="toggleUser(scope.row)">{{ scope.row.status ? '禁用' : '启用' }}</el-button></template></el-table-column>
      </el-table>
    </div>

    <div v-else-if="activeSection === 'resources'" class="admin-resource-grid">
      <div class="management-surface admin-panel admin-courses">
        <div class="surface-heading admin-panel-heading"><div><strong>课程监管</strong><span>跨教师查看并处理发布状态</span></div></div>
        <div class="admin-filters resource-filters">
          <el-input v-model="courseFilters.keyword" clearable placeholder="搜索课程、教师或工号" @keyup.enter="loadCourses" />
          <el-select v-model="courseFilters.status" placeholder="全部状态"><el-option label="全部状态" value="" /><el-option label="草稿" value="DRAFT" /><el-option label="已发布" value="PUBLISHED" /><el-option label="已下线" value="OFFLINE" /></el-select>
          <el-button type="primary" @click="loadCourses">查询课程</el-button>
        </div>
        <el-table :data="courses" max-height="470" empty-text="没有符合条件的课程">
          <el-table-column label="课程" min-width="185"><template #default="scope"><div class="admin-primary-cell"><strong>{{ scope.row.name }}</strong><span>{{ scope.row.category_name }} · {{ scope.row.teacher_name }}</span></div></template></el-table-column>
          <el-table-column label="资源" width="125"><template #default="scope">{{ scope.row.chapter_count }} 章 · {{ scope.row.ready_video_count }}/{{ scope.row.video_count }} 视频</template></el-table-column>
          <el-table-column label="学生" width="75"><template #default="scope">{{ scope.row.student_count }}</template></el-table-column>
          <el-table-column label="状态" width="90"><template #default="scope"><span :class="['operation-state', `state-${scope.row.status.toLowerCase()}`]">{{ courseStatusLabel(scope.row.status) }}</span></template></el-table-column>
          <el-table-column label="操作" width="105" fixed="right"><template #default="scope"><el-button v-if="scope.row.status === 'PUBLISHED'" link type="warning" @click="changeCourseStatus(scope.row, 'OFFLINE')">下线</el-button><el-button v-else link type="primary" @click="changeCourseStatus(scope.row, 'PUBLISHED')">发布</el-button></template></el-table-column>
        </el-table>
      </div>
      <div class="management-surface admin-panel admin-classes">
        <div class="surface-heading admin-panel-heading"><div><strong>班级监管</strong><span>删除班级不会删除师生账号</span></div></div>
        <div class="admin-filters class-filters"><el-input v-model="classKeyword" clearable placeholder="搜索班级、教师或工号" @keyup.enter="loadClasses" /><el-button type="primary" @click="loadClasses">查询班级</el-button></div>
        <el-table :data="classrooms" max-height="470" empty-text="没有符合条件的班级">
          <el-table-column label="班级" min-width="180"><template #default="scope"><div class="admin-primary-cell"><strong>{{ scope.row.name }}</strong><span>{{ scope.row.description || '暂无说明' }}</span></div></template></el-table-column>
          <el-table-column label="负责教师" min-width="125"><template #default="scope">{{ scope.row.teacher_name }}<br><small>{{ scope.row.teacher_no || '—' }}</small></template></el-table-column>
          <el-table-column prop="member_count" label="学生" width="70" /><el-table-column label="操作" width="90" fixed="right"><template #default="scope"><el-button link type="danger" @click="removeClassroom(scope.row)">删除</el-button></template></el-table-column>
        </el-table>
      </div>
    </div>

    <div v-else-if="activeSection === 'categories'" class="management-surface admin-panel admin-categories">
      <div class="surface-heading admin-panel-heading"><div><strong>课程分类管理</strong><span>控制教师创建课程时可选择的分类</span></div><el-button type="primary" @click="openCategory()">＋ 新建分类</el-button></div>
      <el-table :data="categories" max-height="530" empty-text="暂无课程分类">
        <el-table-column prop="sort_order" label="排序" width="85" /><el-table-column label="分类" min-width="180"><template #default="scope"><div class="admin-primary-cell"><strong>{{ scope.row.name }}</strong><span>{{ scope.row.description || '暂无说明' }}</span></div></template></el-table-column>
        <el-table-column prop="course_count" label="课程数" width="100" /><el-table-column label="状态" width="100"><template #default="scope"><span :class="['account-state', scope.row.status ? 'active' : 'disabled']">{{ scope.row.status ? '启用' : '禁用' }}</span></template></el-table-column>
        <el-table-column label="最后更新" width="150"><template #default="scope">{{ formatDate(scope.row.updated_at) }}</template></el-table-column>
        <el-table-column label="操作" width="150" fixed="right"><template #default="scope"><el-button link @click="openCategory(scope.row)">编辑</el-button><el-button link :type="scope.row.status ? 'danger' : 'primary'" @click="toggleCategory(scope.row)">{{ scope.row.status ? '禁用' : '启用' }}</el-button></template></el-table-column>
      </el-table>
    </div>

    <div v-else class="notice-management admin-panel">
      <div class="notice-management-heading"><div><strong>系统公告</strong><span>{{ notices.length }} 条公告，可编辑下线内容后再次发布</span></div><el-button type="primary" @click="openNotice()">＋ 新建公告</el-button></div>
      <div class="admin-notice-list">
        <article v-for="notice in notices" :key="notice.id"><div><span :class="['notice-state', `state-${notice.status.toLowerCase()}`]">{{ noticeStatusLabel(notice.status) }}</span><small>{{ formatDate(notice.publish_time || notice.created_at) }}</small></div><h3>{{ notice.title }}</h3><p>{{ notice.content }}</p><footer><el-button v-if="notice.status !== 'PUBLISHED'" link @click="openNotice(notice)">编辑</el-button><el-button v-if="notice.status !== 'PUBLISHED'" link type="primary" @click="changeNoticeStatus(notice, 'PUBLISHED')">发布</el-button><el-button v-else link type="warning" @click="changeNoticeStatus(notice, 'OFFLINE')">下线</el-button><el-button v-if="notice.status !== 'PUBLISHED'" link type="danger" @click="removeNotice(notice)">删除</el-button></footer></article>
        <el-empty v-if="!notices.length" description="暂无公告" :image-size="60" />
      </div>
    </div>

    <el-dialog v-model="userDialog" title="创建教师或学生账号" width="min(620px, 94vw)" :close-on-click-modal="!saving" :close-on-press-escape="!saving" :show-close="!saving" @closed="resetUserForm">
      <el-form ref="userFormRef" :model="userForm" :rules="userRules" label-position="top"><el-form-item label="账号角色"><el-radio-group v-model="userForm.role"><el-radio-button value="STUDENT">学生</el-radio-button><el-radio-button value="TEACHER">教师</el-radio-button></el-radio-group></el-form-item><div class="admin-form-grid"><el-form-item label="用户名" prop="username"><el-input v-model.trim="userForm.username" placeholder="3–50 位字符" /></el-form-item><el-form-item label="真实姓名" prop="real_name"><el-input v-model.trim="userForm.real_name" placeholder="请输入姓名" /></el-form-item><el-form-item :label="userForm.role === 'STUDENT' ? '学号' : '工号'" :prop="userForm.role === 'STUDENT' ? 'student_no' : 'teacher_no'"><el-input v-if="userForm.role === 'STUDENT'" v-model.trim="userForm.student_no" placeholder="请输入学号" /><el-input v-else v-model.trim="userForm.teacher_no" placeholder="请输入工号" /></el-form-item><el-form-item label="初始密码" prop="password"><el-input v-model="userForm.password" type="password" show-password placeholder="至少 8 位" /></el-form-item><el-form-item label="邮箱" prop="email"><el-input v-model.trim="userForm.email" maxlength="100" placeholder="可选" /></el-form-item><el-form-item label="手机号" prop="phone"><el-input v-model.trim="userForm.phone" maxlength="11" placeholder="可选" /></el-form-item></div></el-form>
      <template #footer><el-button :disabled="saving" @click="userDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="createUser">创建账号</el-button></template>
    </el-dialog>
    <el-dialog v-model="categoryDialog" :title="editingCategoryId ? '编辑课程分类' : '新建课程分类'" width="min(560px, 94vw)">
      <el-form :model="categoryForm" label-position="top"><el-form-item label="分类名称" required><el-input v-model.trim="categoryForm.name" maxlength="50" show-word-limit placeholder="例如：计算机基础" /></el-form-item><el-form-item label="分类说明"><el-input v-model.trim="categoryForm.description" type="textarea" :rows="4" maxlength="255" show-word-limit placeholder="说明该分类包含的课程范围" /></el-form-item><el-form-item label="排序"><el-input-number v-model="categoryForm.sort_order" :min="0" :max="100000" /></el-form-item></el-form>
      <template #footer><el-button :disabled="saving" @click="categoryDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveCategory">保存分类</el-button></template>
    </el-dialog>
    <el-dialog v-model="noticeDialog" :title="editingNoticeId ? '编辑公告' : '新建公告'" width="min(620px, 94vw)">
      <el-form :model="noticeForm" label-position="top"><el-form-item label="公告标题" required><el-input v-model.trim="noticeForm.title" maxlength="200" show-word-limit placeholder="请输入公告标题" /></el-form-item><el-form-item label="公告内容" required><el-input v-model.trim="noticeForm.content" type="textarea" :rows="8" maxlength="50000" placeholder="请输入公告内容" /></el-form-item></el-form>
      <template #footer><el-button :disabled="saving" @click="noticeDialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveNotice">保存公告</el-button></template>
    </el-dialog>
  </section>
</template>
