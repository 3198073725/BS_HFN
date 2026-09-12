<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'

import api from '../api/client'


const loading = ref(false)
const saving = ref(false)
const overview = ref({})
const users = ref([])
const notices = ref([])
const userDialog = ref(false)
const noticeDialog = ref(false)
const userFormRef = ref(null)
const editingNoticeId = ref(null)
const filters = reactive({ role: '', status: '', keyword: '' })
const userForm = reactive({
  role: 'STUDENT',
  username: '',
  password: '',
  real_name: '',
  student_no: '',
  teacher_no: '',
  email: '',
  phone: '',
})
const noticeForm = reactive({ title: '', content: '' })
let userSearchSequence = 0
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

const metrics = computed(() => [
  { label: '系统用户', value: overview.value.users || 0, detail: '活跃 ' + (overview.value.active_users || 0) },
  { label: '学生 / 教师', value: (overview.value.students || 0) + ' / ' + (overview.value.teachers || 0), detail: '账号结构' },
  { label: '已发布课程', value: overview.value.published_courses || 0, detail: '全部 ' + (overview.value.courses || 0) },
  { label: '可学习视频', value: overview.value.ready_videos || 0, detail: 'FFmpeg 已处理' },
  { label: '学习记录', value: overview.value.learning_records || 0, detail: '实时累计' },
  { label: '作业 / 测验提交', value: (overview.value.homework_submissions || 0) + ' / ' + (overview.value.exam_records || 0), detail: '业务记录' },
])

function userParams() {
  const params = {}
  if (filters.role) params.role = filters.role
  if (filters.status) params.status = filters.status
  if (filters.keyword.trim()) params.keyword = filters.keyword.trim()
  return params
}

async function load() {
  const requestId = ++userSearchSequence
  loading.value = true
  try {
    const [statsResponse, userResponse, noticeResponse] = await Promise.all([
      api.get('/statistics'),
      api.get('/admin/users', { params: userParams() }),
      api.get('/notices/manage'),
    ])
    overview.value = statsResponse.data
    if (requestId === userSearchSequence) users.value = userResponse.data
    notices.value = noticeResponse.data
  } catch (error) {
    ElMessage.error(error.message || '后台数据加载失败')
  } finally {
    loading.value = false
  }
}

async function searchUsers() {
  const requestId = ++userSearchSequence
  try {
    const response = await api.get('/admin/users', { params: userParams() })
    if (requestId === userSearchSequence) users.value = response.data
  } catch (error) {
    if (requestId === userSearchSequence) ElMessage.error(error.message || '用户查询失败')
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
    await load()
  } catch (error) {
    ElMessage.error(error.message || '用户创建失败')
  } finally {
    saving.value = false
  }
}

async function toggleUser(user) {
  const nextStatus = !user.status
  try {
    await ElMessageBox.confirm(
      nextStatus ? '确认启用该用户账号？' : '禁用后该用户将无法继续访问受保护功能，确认继续？',
      nextStatus ? '启用用户' : '禁用用户',
      { type: nextStatus ? 'info' : 'warning' },
    )
    const response = await api.put('/admin/users/' + user.id + '/status', { status: nextStatus })
    const index = users.value.findIndex((item) => item.id === user.id)
    if (index >= 0) users.value[index] = response.data
    ElMessage.success(nextStatus ? '用户已启用' : '用户已禁用')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '用户状态更新失败')
  }
}

function openNotice(notice = null) {
  editingNoticeId.value = notice?.id || null
  noticeForm.title = notice?.title || ''
  noticeForm.content = notice?.content || ''
  noticeDialog.value = true
}

async function saveNotice() {
  if (!noticeForm.title.trim() || !noticeForm.content.trim()) {
    ElMessage.warning('请填写公告标题和内容')
    return
  }
  saving.value = true
  try {
    if (editingNoticeId.value) {
      await api.put('/notices/' + editingNoticeId.value, noticeForm)
      ElMessage.success('公告已更新')
    } else {
      await api.post('/notices', noticeForm)
      ElMessage.success('公告草稿已创建')
    }
    noticeDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(error.message || '公告保存失败')
  } finally {
    saving.value = false
  }
}

async function changeNoticeStatus(notice, status) {
  try {
    const response = await api.put('/notices/' + notice.id + '/status', { status })
    const index = notices.value.findIndex((item) => item.id === notice.id)
    if (index >= 0) notices.value[index] = response.data
    ElMessage.success(status === 'PUBLISHED' ? '公告已发布' : '公告已下线')
  } catch (error) {
    ElMessage.error(error.message || '公告状态更新失败')
  }
}

async function removeNotice(notice) {
  try {
    await ElMessageBox.confirm('确认删除这份公告？', '删除公告', { type: 'warning' })
    await api.delete('/notices/' + notice.id)
    notices.value = notices.value.filter((item) => item.id !== notice.id)
    ElMessage.success('公告已删除')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '公告删除失败')
  }
}

function resetUserForm() {
  Object.assign(userForm, {
    role: 'STUDENT',
    username: '',
    password: '',
    real_name: '',
    student_no: '',
    teacher_no: '',
    email: '',
    phone: '',
  })
  userFormRef.value?.clearValidate()
}

watch(() => userForm.role, (role) => {
  if (role === 'STUDENT') userForm.teacher_no = ''
  if (role === 'TEACHER') userForm.student_no = ''
  userFormRef.value?.clearValidate(['student_no', 'teacher_no'])
})

function roleLabel(role) {
  return { ADMIN: '管理员', TEACHER: '教师', STUDENT: '学生' }[role] || role
}

function noticeStatusLabel(status) {
  return { DRAFT: '草稿', PUBLISHED: '已发布', OFFLINE: '已下线' }[status] || status
}

function formatDate(value) {
  if (!value) return '—'
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : value + 'Z'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(normalized))
}

onMounted(load)
</script>

<template>
  <section class="page-section admin-dashboard" v-loading="loading">
    <div class="page-heading">
      <div>
        <p class="eyebrow">SYSTEM CONSOLE</p>
        <h1>系统后台</h1>
        <p>管理教师与学生账号、系统公告，并查看核心业务规模。</p>
      </div>
    </div>

    <div class="admin-metrics">
      <article v-for="metric in metrics" :key="metric.label">
        <span>{{ metric.label }}</span>
        <strong>{{ metric.value }}</strong>
        <small>{{ metric.detail }}</small>
      </article>
    </div>

    <div class="admin-layout">
      <div class="management-surface admin-users">
        <div class="surface-heading">
          <div><strong>用户管理</strong><span>{{ users.length }} 条结果</span></div>
          <el-button type="primary" @click="userDialog = true">＋ 创建用户</el-button>
        </div>
        <div class="admin-filters">
          <el-input v-model="filters.keyword" clearable placeholder="搜索用户名、姓名、学号或工号" @keyup.enter="searchUsers" />
          <el-select v-model="filters.role" placeholder="全部角色">
            <el-option label="全部角色" value="" />
            <el-option label="学生" value="STUDENT" />
            <el-option label="教师" value="TEACHER" />
            <el-option label="管理员" value="ADMIN" />
          </el-select>
          <el-select v-model="filters.status" placeholder="全部状态">
            <el-option label="全部状态" value="" />
            <el-option label="正常" value="true" />
            <el-option label="已禁用" value="false" />
          </el-select>
          <el-button @click="searchUsers">查询</el-button>
        </div>
        <p class="table-scroll-hint">左右滑动表格可查看账号状态和操作</p>
        <el-table :data="users" max-height="460">
          <el-table-column prop="username" label="用户名" min-width="130" />
          <el-table-column prop="real_name" label="姓名" min-width="110" />
          <el-table-column label="角色" width="100">
            <template #default="scope">{{ roleLabel(scope.row.role) }}</template>
          </el-table-column>
          <el-table-column label="学号 / 工号" min-width="130">
            <template #default="scope">{{ scope.row.student_no || scope.row.teacher_no || '—' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="scope">
              <span :class="['account-state', scope.row.status ? 'active' : 'disabled']">
                {{ scope.row.status ? '正常' : '禁用' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="scope">
              <el-button
                v-if="scope.row.role !== 'ADMIN'"
                link
                :type="scope.row.status ? 'danger' : 'primary'"
                @click="toggleUser(scope.row)"
              >
                {{ scope.row.status ? '禁用' : '启用' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <aside class="notice-management">
        <div class="notice-management-heading">
          <div><strong>系统公告</strong><span>{{ notices.length }} 条</span></div>
          <el-button type="primary" @click="openNotice()">新建</el-button>
        </div>
        <article v-for="notice in notices" :key="notice.id">
          <div>
            <span :class="['notice-state', 'state-' + notice.status.toLowerCase()]">
              {{ noticeStatusLabel(notice.status) }}
            </span>
            <small>{{ formatDate(notice.publish_time || notice.created_at) }}</small>
          </div>
          <h3>{{ notice.title }}</h3>
          <p>{{ notice.content }}</p>
          <footer>
            <el-button v-if="notice.status !== 'PUBLISHED'" link @click="openNotice(notice)">编辑</el-button>
            <el-button
              v-if="notice.status !== 'PUBLISHED'"
              link
              type="primary"
              @click="changeNoticeStatus(notice, 'PUBLISHED')"
            >发布</el-button>
            <el-button
              v-else
              link
              type="warning"
              @click="changeNoticeStatus(notice, 'OFFLINE')"
            >下线</el-button>
            <el-button v-if="notice.status !== 'PUBLISHED'" link type="danger" @click="removeNotice(notice)">删除</el-button>
          </footer>
        </article>
        <el-empty v-if="!notices.length" description="暂无公告" :image-size="60" />
      </aside>
    </div>

    <el-dialog
      v-model="userDialog"
      title="创建教师或学生账号"
      width="min(620px, 94vw)"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      @closed="resetUserForm"
    >
      <el-form ref="userFormRef" :model="userForm" :rules="userRules" label-position="top">
        <el-form-item label="账号角色">
          <el-radio-group v-model="userForm.role">
            <el-radio-button value="STUDENT">学生</el-radio-button>
            <el-radio-button value="TEACHER">教师</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <div class="admin-form-grid">
          <el-form-item label="用户名" prop="username"><el-input v-model.trim="userForm.username" placeholder="3–50 位字符" /></el-form-item>
          <el-form-item label="真实姓名" prop="real_name"><el-input v-model.trim="userForm.real_name" placeholder="请输入姓名" /></el-form-item>
          <el-form-item :label="userForm.role === 'STUDENT' ? '学号' : '工号'" :prop="userForm.role === 'STUDENT' ? 'student_no' : 'teacher_no'">
            <el-input v-if="userForm.role === 'STUDENT'" v-model.trim="userForm.student_no" placeholder="请输入学号" />
            <el-input v-else v-model.trim="userForm.teacher_no" placeholder="请输入工号" />
          </el-form-item>
          <el-form-item label="初始密码" prop="password">
            <el-input v-model="userForm.password" type="password" show-password placeholder="至少 8 位" />
          </el-form-item>
          <el-form-item label="邮箱" prop="email"><el-input v-model.trim="userForm.email" maxlength="100" placeholder="可选" /></el-form-item>
          <el-form-item label="手机号" prop="phone"><el-input v-model.trim="userForm.phone" maxlength="11" placeholder="可选" /></el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="userDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="createUser">创建账号</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="noticeDialog" :title="editingNoticeId ? '编辑公告' : '新建公告'" width="min(620px, 94vw)">
      <el-form :model="noticeForm" label-position="top">
        <el-form-item label="公告标题" required>
          <el-input v-model.trim="noticeForm.title" maxlength="200" show-word-limit placeholder="请输入公告标题" />
        </el-form-item>
        <el-form-item label="公告内容" required>
          <el-input v-model.trim="noticeForm.content" type="textarea" :rows="8" maxlength="50000" placeholder="请输入公告内容" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="noticeDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveNotice">保存公告</el-button>
      </template>
    </el-dialog>
  </section>
</template>
