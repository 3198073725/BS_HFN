<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import api from '../api/client'
import { useAuthStore } from '../stores/auth'


const auth = useAuthStore()
const route = useRoute()
const isTeacher = computed(() => auth.user?.role === 'TEACHER')
const classrooms = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingClassId = ref(null)
const formRef = ref(null)
const addingClassId = ref(null)
const removingStudentKey = ref('')
const teacherCourses = ref([])
const assigningClassId = ref(null)
const removingCourseKey = ref('')
const accountInputs = reactive({})
const courseSelections = reactive({})
const selectedClassId = ref(null)
const classKeyword = ref('')
const classStatistics = ref(null)
const statisticsLoading = ref(false)
const passwordResetRequests = ref([])
const handlingResetId = ref(null)
let requestSequence = 0
let statisticsRequestSequence = 0

const form = reactive({
  name: '',
  description: '',
})

const rules = {
  name: [
    { required: true, message: '请输入班级名称', trigger: 'blur' },
    { min: 1, max: 100, message: '班级名称不能超过 100 位', trigger: 'blur' },
  ],
  description: [
    { max: 500, message: '班级说明不能超过 500 位', trigger: 'blur' },
  ],
}

const totalMembers = computed(() => classrooms.value.reduce(
  (total, classroom) => total + Number(classroom.member_count || 0),
  0,
))
const totalCourseAssignments = computed(() => classrooms.value.reduce(
  (total, classroom) => total + Number(classroom.course_count || 0),
  0,
))

const filteredClassrooms = computed(() => {
  const keyword = classKeyword.value.trim().toLowerCase()
  if (!keyword) return classrooms.value
  return classrooms.value.filter((classroom) => [classroom.name, classroom.description]
    .some((value) => String(value || '').toLowerCase().includes(keyword)))
})

const selectedClassroom = computed(() => {
  if (!isTeacher.value || !filteredClassrooms.value.length) return null
  return filteredClassrooms.value.find((classroom) => classroom.id === selectedClassId.value)
    || filteredClassrooms.value[0]
})

const displayedClassrooms = computed(() => (
  isTeacher.value
    ? (selectedClassroom.value ? [selectedClassroom.value] : [])
    : classrooms.value
))

watch(filteredClassrooms, (items) => {
  if (isTeacher.value && items.length && !items.some((item) => item.id === selectedClassId.value)) {
    selectedClassId.value = items[0].id
  }
})

watch(selectedClassId, (classId) => {
  void loadClassStatistics(classId)
})

function formatDate(value) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date(value))
}

async function loadClasses() {
  const requestId = ++requestSequence
  loading.value = true
  try {
    const [response, courseResponse, resetResponse] = await Promise.all([
      api.get('/classes'),
      isTeacher.value ? api.get('/classes/course-options') : Promise.resolve({ data: [] }),
      isTeacher.value ? api.get('/classes/password-reset-requests') : Promise.resolve({ data: [] }),
    ])
    if (requestId !== requestSequence) return
    classrooms.value = response.data
    teacherCourses.value = courseResponse.data
    passwordResetRequests.value = resetResponse.data
    const requestedId = Number(route.query.reset_request_id)
    const requestedItem = passwordResetRequests.value.find((item) => item.id === requestedId)
    if (requestedItem?.class_ids?.length) selectedClassId.value = requestedItem.class_ids[0]
    if (isTeacher.value && !classrooms.value.some((item) => item.id === selectedClassId.value)) {
      selectedClassId.value = classrooms.value[0]?.id || null
    }
  } catch (error) {
    if (requestId === requestSequence) {
      ElMessage.error(error.message || '班级信息加载失败')
    }
  } finally {
    if (requestId === requestSequence) loading.value = false
  }
}

function resetRequestsForClass(classId) {
  return passwordResetRequests.value.filter((item) => item.class_ids?.includes(classId))
}

async function reviewPasswordReset(item, action) {
  if (handlingResetId.value !== null) return
  const approved = action === 'APPROVED'
  try {
    await ElMessageBox.confirm(
      approved
        ? `同意后，“${item.student_name}”申请时填写的新密码将立即生效，确定继续吗？`
        : `确定拒绝“${item.student_name}”的密码重置申请吗？`,
      approved ? '同意密码重置' : '拒绝密码重置',
      {
        confirmButtonText: approved ? '确认同意' : '确认拒绝',
        cancelButtonText: '取消',
        type: approved ? 'warning' : 'info',
      },
    )
  } catch {
    return
  }
  handlingResetId.value = item.id
  try {
    const response = await api.put(`/classes/password-reset-requests/${item.id}`, { action })
    passwordResetRequests.value = passwordResetRequests.value.filter((request) => request.id !== item.id)
    ElMessage.success(response.message || (approved ? '已同意密码重置' : '已拒绝密码重置'))
  } catch (error) {
    ElMessage.error(error.message || '密码重置申请处理失败')
    await loadClasses()
  } finally {
    handlingResetId.value = null
  }
}

async function loadClassStatistics(classId = selectedClassId.value) {
  const requestId = ++statisticsRequestSequence
  if (!isTeacher.value || !classId) {
    classStatistics.value = null
    statisticsLoading.value = false
    return
  }
  statisticsLoading.value = true
  try {
    const response = await api.get(`/statistics/classes/${classId}`)
    if (requestId === statisticsRequestSequence) classStatistics.value = response.data
  } catch (error) {
    if (requestId === statisticsRequestSequence) {
      classStatistics.value = null
      ElMessage.error(error.message || '班级教学统计加载失败')
    }
  } finally {
    if (requestId === statisticsRequestSequence) statisticsLoading.value = false
  }
}

function availableCourses(classroom) {
  const assignedIds = new Set((classroom.courses || []).map((course) => course.id))
  return teacherCourses.value.filter((course) => !assignedIds.has(course.id))
}

function courseStatusLabel(status) {
  return { DRAFT: '草稿', PUBLISHED: '已发布', OFFLINE: '已下线' }[status] || status
}

function replaceClassroom(classroom) {
  const index = classrooms.value.findIndex((item) => item.id === classroom.id)
  if (index === -1) {
    classrooms.value.unshift(classroom)
  } else {
    classrooms.value.splice(index, 1, classroom)
  }
  if (classroom.id === selectedClassId.value) void loadClassStatistics(classroom.id)
}

function openCreateDialog() {
  editingClassId.value = null
  form.name = ''
  form.description = ''
  dialogVisible.value = true
}

function openEditDialog(classroom) {
  editingClassId.value = classroom.id
  form.name = classroom.name
  form.description = classroom.description || ''
  dialogVisible.value = true
}

function resetDialog() {
  if (saving.value) return
  editingClassId.value = null
  form.name = ''
  form.description = ''
  formRef.value?.clearValidate()
}

async function saveClassroom() {
  if (saving.value) return
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || null,
    }
    const response = editingClassId.value
      ? await api.put(`/classes/${editingClassId.value}`, payload)
      : await api.post('/classes', payload)
    replaceClassroom(response.data)
    selectedClassId.value = response.data.id
    classKeyword.value = ''
    ElMessage.success(editingClassId.value ? '班级信息已更新' : '班级创建成功')
    dialogVisible.value = false
  } catch (error) {
    ElMessage.error(error.message || '班级保存失败')
  } finally {
    saving.value = false
  }
}

async function deleteClassroom(classroom) {
  try {
    await ElMessageBox.confirm(
      `删除“${classroom.name}”后将同时清空其成员关系，确定继续吗？`,
      '删除班级',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await api.delete(`/classes/${classroom.id}`)
    classrooms.value = classrooms.value.filter((item) => item.id !== classroom.id)
    if (selectedClassId.value === classroom.id) {
      selectedClassId.value = classrooms.value[0]?.id || null
    }
    delete accountInputs[classroom.id]
    ElMessage.success('班级已删除')
  } catch (error) {
    ElMessage.error(error.message || '班级删除失败')
  }
}

async function addStudent(classroom) {
  const account = String(accountInputs[classroom.id] || '').trim()
  if (!account) {
    ElMessage.warning('请输入学生用户名、学号或邮箱')
    return
  }
  if (addingClassId.value !== null) return
  addingClassId.value = classroom.id
  try {
    const response = await api.post(`/classes/${classroom.id}/students`, { account })
    replaceClassroom(response.data)
    accountInputs[classroom.id] = ''
    ElMessage.success('学生已加入班级')
  } catch (error) {
    ElMessage.error(error.message || '添加学生失败')
  } finally {
    addingClassId.value = null
  }
}

async function removeStudent(classroom, student) {
  try {
    await ElMessageBox.confirm(
      `确定将“${student.real_name}”移出“${classroom.name}”吗？`,
      '移出学生',
      { confirmButtonText: '确认移出', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  const operationKey = `${classroom.id}:${student.id}`
  removingStudentKey.value = operationKey
  try {
    const response = await api.delete(`/classes/${classroom.id}/students/${student.id}`)
    replaceClassroom(response.data)
    ElMessage.success('学生已移出班级')
  } catch (error) {
    ElMessage.error(error.message || '移出学生失败')
  } finally {
    removingStudentKey.value = ''
  }
}

async function assignCourse(classroom) {
  const courseId = Number(courseSelections[classroom.id])
  if (!courseId) {
    ElMessage.warning('请选择要关联的课程')
    return
  }
  if (assigningClassId.value !== null) return
  assigningClassId.value = classroom.id
  try {
    const response = await api.post(`/classes/${classroom.id}/courses`, { course_id: courseId })
    replaceClassroom(response.data)
    courseSelections[classroom.id] = null
    ElMessage.success('课程已关联，班级学生已同步加入')
  } catch (error) {
    ElMessage.error(error.message || '关联课程失败')
  } finally {
    assigningClassId.value = null
  }
}

async function removeCourseAssignment(classroom, course) {
  try {
    await ElMessageBox.confirm(
      `解除“${course.name}”与“${classroom.name}”的关联吗？学生已有学习记录会保留。`,
      '解除课程关联',
      { confirmButtonText: '解除关联', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  const operationKey = `${classroom.id}:${course.id}`
  removingCourseKey.value = operationKey
  try {
    const response = await api.delete(`/classes/${classroom.id}/courses/${course.id}`)
    replaceClassroom(response.data)
    ElMessage.success('班级课程关联已解除')
  } catch (error) {
    ElMessage.error(error.message || '解除课程关联失败')
  } finally {
    removingCourseKey.value = ''
  }
}

onMounted(loadClasses)
onBeforeUnmount(() => {
  requestSequence += 1
  statisticsRequestSequence += 1
})
</script>

<template>
  <section class="page-section classroom-page" v-loading="loading">
    <div class="page-heading">
      <div>
        <p class="eyebrow">班级与成员</p>
        <h1>{{ isTeacher ? '班级管理' : '我的班级' }}</h1>
        <p>
          {{ isTeacher ? '集中维护班级和学生名册，让后续教学管理更清晰。' : '查看你已经加入的班级和负责教师。' }}
        </p>
      </div>
      <el-button v-if="isTeacher" type="primary" @click="openCreateDialog">＋ 创建班级</el-button>
    </div>

    <div v-if="isTeacher" class="classroom-overview" aria-label="班级概览">
      <article>
        <span>我管理的班级</span>
        <strong>{{ classrooms.length }}</strong>
        <small>个教学班级</small>
      </article>
      <article>
        <span>当前名册人数</span>
        <strong>{{ totalMembers }}</strong>
        <small>按班级成员关系统计</small>
      </article>
      <article>
        <span>已关联课程</span>
        <strong>{{ totalCourseAssignments }}</strong>
        <small>按班级课程关系统计</small>
      </article>
      <p>关联课程会将当前名册整班加入，后续新增学生也会自动同步；解除关联不会删除已有学习记录。</p>
    </div>

    <div v-if="classrooms.length" :class="isTeacher ? 'classroom-workspace' : 'classroom-grid'">
      <aside v-if="isTeacher" class="classroom-list-panel" aria-label="班级列表">
        <div class="classroom-list-heading">
          <div><strong>班级列表</strong><small>共 {{ classrooms.length }} 个</small></div>
        </div>
        <div class="classroom-list-search">
          <el-input v-model="classKeyword" clearable placeholder="搜索班级名称或说明" />
        </div>
        <div class="classroom-list" role="listbox" aria-label="选择要管理的班级">
          <button
            v-for="(classroom, index) in filteredClassrooms"
            :key="classroom.id"
            :class="{ active: classroom.id === selectedClassroom?.id }"
            type="button"
            role="option"
            :aria-selected="classroom.id === selectedClassroom?.id"
            @click="selectedClassId = classroom.id"
          >
            <span>{{ String(index + 1).padStart(2, '0') }}</span>
            <div>
              <strong>{{ classroom.name }}</strong>
              <small>{{ classroom.member_count }} 名学生</small>
              <em v-if="resetRequestsForClass(classroom.id).length">
                {{ resetRequestsForClass(classroom.id).length }} 项密码申请
              </em>
            </div>
          </button>
          <el-empty v-if="!filteredClassrooms.length" :image-size="54" description="没有匹配的班级" />
        </div>
        <p>选择一个班级后，在右侧维护班级资料和学生名册。</p>
      </aside>

      <el-select
        v-if="isTeacher"
        v-model="selectedClassId"
        class="classroom-mobile-selector"
        filterable
        placeholder="选择要管理的班级"
      >
        <el-option
          v-for="classroom in classrooms"
          :key="classroom.id"
          :label="`${classroom.name}（${classroom.member_count} 人）`"
          :value="classroom.id"
        />
      </el-select>

      <div v-if="isTeacher && !selectedClassroom" class="surface-card classroom-selection-empty">
        <el-empty description="没有匹配的班级，请调整搜索条件" />
      </div>

      <article v-for="(classroom, index) in displayedClassrooms" :key="classroom.id" class="classroom-card">
        <header class="classroom-card-header">
          <div class="classroom-title-group">
            <span class="classroom-mark">{{ isTeacher ? '班' : String(index + 1).padStart(2, '0') }}</span>
            <div>
              <p>{{ isTeacher ? '教学班级' : '所在班级' }}</p>
              <h2>{{ classroom.name }}</h2>
            </div>
          </div>
          <div v-if="isTeacher" class="classroom-actions">
            <el-button text type="primary" @click="openEditDialog(classroom)">编辑</el-button>
            <el-button text type="danger" @click="deleteClassroom(classroom)">删除</el-button>
          </div>
        </header>

        <p class="classroom-description">{{ classroom.description || '暂未填写班级说明。' }}</p>
        <div class="classroom-facts">
          <span><strong>{{ classroom.member_count }}</strong> 名学生</span>
          <span><strong>{{ classroom.course_count }}</strong> 门课程</span>
          <span v-if="!isTeacher">负责教师 · {{ classroom.teacher_name }}</span>
          <span v-if="!isTeacher && classroom.teacher_no">工号 · {{ classroom.teacher_no }}</span>
          <span>{{ isTeacher ? '创建' : '加入' }} · {{ formatDate(isTeacher ? classroom.created_at : classroom.joined_at) }}</span>
        </div>

        <section v-if="isTeacher" class="classroom-progress-panel" aria-label="班级教学进展" v-loading="statisticsLoading">
          <div class="classroom-progress-heading">
            <div>
              <strong>教学进展</strong>
              <small>按当前班级名册和已关联课程统计</small>
            </div>
            <el-button text :disabled="statisticsLoading" @click="loadClassStatistics(classroom.id)">刷新</el-button>
          </div>
          <template v-if="classStatistics">
            <div class="classroom-progress-overview">
              <article>
                <span>平均视频进度</span>
                <strong>{{ classStatistics.overview.average_progress }}%</strong>
                <small>{{ classStatistics.overview.ready_video_count }} 个可播放视频</small>
              </article>
              <article>
                <span>作业提交率</span>
                <strong>{{ classStatistics.overview.homework_submission_rate }}%</strong>
                <small>{{ classStatistics.overview.homework_count }} 项已发布作业</small>
              </article>
              <article>
                <span>作业平均分</span>
                <strong>{{ classStatistics.overview.average_homework_percent }}%</strong>
                <small>仅统计已批改作业</small>
              </article>
              <article>
                <span>测验完成率</span>
                <strong>{{ classStatistics.overview.exam_completion_rate }}%</strong>
                <small>{{ classStatistics.overview.exam_count }} 项已发布测验</small>
              </article>
              <article>
                <span>测验平均分</span>
                <strong>{{ classStatistics.overview.average_exam_percent }}%</strong>
                <small>仅统计已交卷记录</small>
              </article>
            </div>
            <div v-if="classStatistics.courses.length" class="classroom-course-progress-list">
              <article v-for="course in classStatistics.courses" :key="course.course_id">
                <div>
                  <strong>{{ course.course_name }}</strong>
                  <small>{{ courseStatusLabel(course.status) }} · {{ course.enrolled_count }}/{{ course.member_count }} 人已加入</small>
                </div>
                <span><small>视频进度</small><strong>{{ course.average_progress }}%</strong></span>
                <span><small>作业提交</small><strong>{{ course.homework_submission_rate }}%</strong></span>
                <span><small>测验完成</small><strong>{{ course.exam_completion_rate }}%</strong></span>
              </article>
            </div>
            <p v-else class="classroom-progress-empty">关联课程后，这里会展示视频、作业和测验进展。</p>
          </template>
          <p v-else-if="!statisticsLoading" class="classroom-progress-empty">暂时无法读取班级教学进展。</p>
        </section>

        <section class="classroom-course-panel" aria-label="班级课程">
          <div class="classroom-course-heading">
            <div>
              <strong>班级课程</strong>
              <small>{{ isTeacher ? '关联后将名册学生同步加入课程' : '由负责教师统一安排' }}</small>
            </div>
            <div v-if="isTeacher" class="classroom-course-picker">
              <el-select
                v-model="courseSelections[classroom.id]"
                filterable
                clearable
                :disabled="!availableCourses(classroom).length"
                :placeholder="availableCourses(classroom).length ? '选择我的课程' : '暂无可关联课程'"
              >
                <el-option
                  v-for="course in availableCourses(classroom)"
                  :key="course.id"
                  :label="`${course.name}（${courseStatusLabel(course.status)}）`"
                  :value="course.id"
                />
              </el-select>
              <el-button
                type="primary"
                :loading="assigningClassId === classroom.id"
                :disabled="!availableCourses(classroom).length"
                @click="assignCourse(classroom)"
              >关联课程</el-button>
            </div>
          </div>

          <div v-if="classroom.courses?.length" class="classroom-course-list">
            <article v-for="course in classroom.courses" :key="course.id">
              <router-link :to="`/courses/${course.id}`">
                <span class="classroom-course-cover" :style="course.cover_url ? { backgroundImage: `url(${course.cover_url})` } : {}">
                  <b v-if="!course.cover_url">{{ course.name.slice(0, 1) }}</b>
                </span>
                <span>
                  <strong>{{ course.name }}</strong>
                  <small>{{ course.category_name || '未分类' }} · {{ courseStatusLabel(course.status) }}</small>
                </span>
              </router-link>
              <el-button
                v-if="isTeacher"
                text
                :loading="removingCourseKey === `${classroom.id}:${course.id}`"
                @click="removeCourseAssignment(classroom, course)"
              >解除</el-button>
            </article>
          </div>
          <div v-else class="classroom-course-empty">
            {{ isTeacher ? '当前班级还没有关联课程' : '负责教师暂未安排班级课程' }}
            <router-link v-if="isTeacher && !teacherCourses.length" to="/teacher/courses">先创建课程</router-link>
          </div>
        </section>

        <template v-if="isTeacher">
          <section
            v-if="resetRequestsForClass(classroom.id).length"
            class="classroom-reset-panel"
            aria-label="学生密码重置申请"
          >
            <div class="classroom-reset-heading">
              <div>
                <strong>密码重置申请</strong>
                <small>确认学生身份后再同意，新密码会立即生效</small>
              </div>
              <span>{{ resetRequestsForClass(classroom.id).length }} 项待处理</span>
            </div>
            <article
              v-for="item in resetRequestsForClass(classroom.id)"
              :key="item.id"
              class="classroom-reset-item"
            >
              <div class="classroom-reset-student">
                <span>{{ item.student_name.slice(0, 1) }}</span>
                <p>
                  <strong>{{ item.student_name }}</strong>
                  <small>{{ item.student_no || item.username }} · {{ item.class_names.join('、') }}</small>
                </p>
              </div>
              <time>申请于 {{ formatDate(item.requested_at) }}</time>
              <div class="classroom-reset-actions">
                <el-button
                  :loading="handlingResetId === item.id"
                  :disabled="handlingResetId !== null && handlingResetId !== item.id"
                  @click="reviewPasswordReset(item, 'REJECTED')"
                >拒绝</el-button>
                <el-button
                  type="primary"
                  :loading="handlingResetId === item.id"
                  :disabled="handlingResetId !== null && handlingResetId !== item.id"
                  @click="reviewPasswordReset(item, 'APPROVED')"
                >同意重置</el-button>
              </div>
            </article>
          </section>

          <div class="classroom-member-toolbar">
            <div>
              <strong>学生名册</strong>
              <small>使用完整账号信息精确添加</small>
            </div>
            <div class="classroom-add-student">
              <el-input
                v-model="accountInputs[classroom.id]"
                maxlength="100"
                placeholder="学生用户名、学号或邮箱"
                @keyup.enter="addStudent(classroom)"
              />
              <el-button
                type="primary"
                :loading="addingClassId === classroom.id"
                :disabled="addingClassId !== null && addingClassId !== classroom.id"
                @click="addStudent(classroom)"
              >
                添加学生
              </el-button>
            </div>
          </div>

          <p class="table-scroll-hint">左右滑动名册可查看学生账号和全部操作</p>
          <el-table :data="classroom.students" empty-text="班级中还没有学生" max-height="340">
            <el-table-column label="学生" min-width="150">
              <template #default="scope">
                <div class="classroom-student-cell">
                  <span>{{ scope.row.real_name.slice(0, 1) }}</span>
                  <div>
                    <strong>{{ scope.row.real_name }}</strong>
                    <small>{{ scope.row.student_no || '未设置学号' }}</small>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="username" label="用户名" min-width="130" />
            <el-table-column label="联系方式" min-width="190">
              <template #default="scope">{{ scope.row.email || scope.row.phone || '—' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="scope">
                <span :class="['classroom-student-state', { disabled: !scope.row.status }]">
                  {{ scope.row.status ? '正常' : '已禁用' }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90" fixed="right">
              <template #default="scope">
                <el-button
                  text
                  type="danger"
                  :loading="removingStudentKey === `${classroom.id}:${scope.row.id}`"
                  @click="removeStudent(classroom, scope.row)"
                >
                  移出
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </template>

        <div v-else class="student-classroom-note">
          <span>{{ classroom.teacher_name.slice(0, 1) }}</span>
          <p><strong>{{ classroom.teacher_name }}</strong><small>班级负责教师</small></p>
        </div>
      </article>
    </div>

    <div v-else-if="!loading" class="surface-card classroom-empty">
      <el-empty :description="isTeacher ? '还没有班级，先创建第一个教学班吧' : '你目前还没有加入任何班级'" />
      <el-button v-if="isTeacher" type="primary" @click="openCreateDialog">创建第一个班级</el-button>
    </div>

    <el-dialog
      v-model="dialogVisible"
      :title="editingClassId ? '编辑班级' : '创建班级'"
      width="min(520px, calc(100vw - 28px))"
      :close-on-click-modal="!saving"
      :close-on-press-escape="!saving"
      :show-close="!saving"
      @closed="resetDialog"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="班级名称" prop="name">
          <el-input v-model="form.name" maxlength="100" show-word-limit placeholder="例如：软件工程 2026 级一班" />
        </el-form-item>
        <el-form-item label="班级说明" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="4"
            maxlength="500"
            show-word-limit
            placeholder="填写年级、专业或教学安排等说明（可选）"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="saving" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveClassroom">
          {{ editingClassId ? '保存修改' : '创建班级' }}
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>
