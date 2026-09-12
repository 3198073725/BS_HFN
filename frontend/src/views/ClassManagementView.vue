<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

import api from '../api/client'
import { useAuthStore } from '../stores/auth'


const auth = useAuthStore()
const isTeacher = computed(() => auth.user?.role === 'TEACHER')
const classrooms = ref([])
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingClassId = ref(null)
const formRef = ref(null)
const addingClassId = ref(null)
const removingStudentKey = ref('')
const accountInputs = reactive({})
const selectedClassId = ref(null)
const classKeyword = ref('')
let requestSequence = 0

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
    const response = await api.get('/classes')
    if (requestId !== requestSequence) return
    classrooms.value = response.data
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

function replaceClassroom(classroom) {
  const index = classrooms.value.findIndex((item) => item.id === classroom.id)
  if (index === -1) {
    classrooms.value.unshift(classroom)
  } else {
    classrooms.value.splice(index, 1, classroom)
  }
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

onMounted(loadClasses)
onBeforeUnmount(() => {
  requestSequence += 1
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
      <p>学生可通过用户名、学号或邮箱加入。移出班级不会删除学生账号，也不会影响其已有课程学习记录。</p>
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
            <div><strong>{{ classroom.name }}</strong><small>{{ classroom.member_count }} 名学生</small></div>
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
          <span v-if="!isTeacher">负责教师 · {{ classroom.teacher_name }}</span>
          <span v-if="!isTeacher && classroom.teacher_no">工号 · {{ classroom.teacher_no }}</span>
          <span>{{ isTeacher ? '创建' : '加入' }} · {{ formatDate(isTeacher ? classroom.created_at : classroom.joined_at) }}</span>
        </div>

        <template v-if="isTeacher">
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
