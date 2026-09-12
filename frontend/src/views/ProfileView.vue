<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import api from '../api/client'
import { useAuthStore } from '../stores/auth'


const route = useRoute()
const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const avatarSaving = ref(false)
const errorMessage = ref('')
const profile = ref(null)
const fileInput = ref(null)
const localAvatarUrl = ref('')
const form = reactive({ real_name: '', email: '', phone: '', bio: '' })
const isOwnProfile = computed(() => route.name === 'my-profile')
const roleLabel = computed(() => ({ ADMIN: '系统管理员', TEACHER: '授课教师', STUDENT: '学生' })[profile.value?.role] || '平台用户')
const avatarSource = computed(() => localAvatarUrl.value || profile.value?.avatar_url || '')

function fillForm(user) {
  Object.assign(form, {
    real_name: user.real_name || '',
    email: user.email || '',
    phone: user.phone || '',
    bio: user.bio || '',
  })
}

async function loadProfile() {
  loading.value = true
  errorMessage.value = ''
  clearLocalAvatar()
  try {
    const response = await api.get(isOwnProfile.value ? '/users/me' : `/users/${route.params.id}`)
    profile.value = response.data
    if (isOwnProfile.value) fillForm(profile.value)
  } catch (error) {
    profile.value = null
    errorMessage.value = error.message || '个人主页加载失败'
  } finally {
    loading.value = false
  }
}

async function saveProfile() {
  const realName = form.real_name.trim()
  if (!realName) {
    ElMessage.warning('请输入姓名')
    return
  }
  saving.value = true
  try {
    const response = await api.put('/users/me', {
      real_name: realName,
      email: form.email.trim() || null,
      phone: form.phone.trim() || null,
      bio: form.bio.trim() || null,
    })
    profile.value = response.data
    auth.updateUser(response.data)
    fillForm(response.data)
    ElMessage.success('个人资料已保存')
  } catch (error) {
    ElMessage.error(error.message || '个人资料保存失败')
  } finally {
    saving.value = false
  }
}

function chooseAvatar() {
  fileInput.value?.click()
}

async function uploadAvatar(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    ElMessage.warning('头像仅支持 JPG、PNG 或 WebP 格式')
    return
  }
  if (file.size > 3 * 1024 * 1024) {
    ElMessage.warning('头像不能超过 3MB')
    return
  }
  clearLocalAvatar()
  localAvatarUrl.value = URL.createObjectURL(file)
  avatarSaving.value = true
  const body = new FormData()
  body.append('avatar', file)
  try {
    const response = await api.post('/users/me/avatar', body)
    profile.value = response.data
    auth.updateUser(response.data)
    clearLocalAvatar()
    ElMessage.success('头像已更新')
  } catch (error) {
    clearLocalAvatar()
    ElMessage.error(error.message || '头像上传失败')
  } finally {
    avatarSaving.value = false
  }
}

async function removeAvatar() {
  try {
    await ElMessageBox.confirm('确认移除当前头像？', '移除头像', { type: 'warning' })
    avatarSaving.value = true
    const response = await api.delete('/users/me/avatar')
    profile.value = response.data
    auth.updateUser(response.data)
    ElMessage.success('头像已移除')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '头像移除失败')
  } finally {
    avatarSaving.value = false
  }
}

function clearLocalAvatar() {
  if (localAvatarUrl.value) URL.revokeObjectURL(localAvatarUrl.value)
  localAvatarUrl.value = ''
}

watch(() => route.fullPath, loadProfile)
onMounted(loadProfile)
onBeforeUnmount(clearLocalAvatar)
</script>

<template>
  <section class="page-section profile-page" v-loading="loading">
    <template v-if="profile">
      <header class="profile-header surface-card">
        <div class="profile-avatar-large">
          <img v-if="avatarSource" :src="avatarSource" alt="" />
          <span v-else>{{ (profile.real_name || '用').slice(0, 1) }}</span>
        </div>
        <div class="profile-identity">
          <p>{{ roleLabel }}</p>
          <h1>{{ profile.real_name }}</h1>
          <div class="profile-meta">
            <span v-if="profile.student_no">学号 {{ profile.student_no }}</span>
            <span v-if="profile.teacher_no">工号 {{ profile.teacher_no }}</span>
            <span>加入于 {{ new Date(profile.created_at).toLocaleDateString('zh-CN') }}</span>
          </div>
        </div>
        <div v-if="isOwnProfile" class="profile-avatar-actions">
          <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" @change="uploadAvatar" />
          <el-button :loading="avatarSaving" @click="chooseAvatar">更换头像</el-button>
          <el-button v-if="profile.avatar_url" :disabled="avatarSaving" @click="removeAvatar">移除</el-button>
          <small>JPG、PNG 或 WebP，不超过 3MB</small>
        </div>
      </header>

      <div v-if="isOwnProfile" class="profile-own-layout">
        <section class="surface-card profile-editor">
          <div class="profile-section-heading">
            <div><p class="eyebrow">个人资料</p><h2>编辑我的主页</h2></div>
            <small>姓名和简介会展示给其他用户；联系方式仅自己和有权限的管理人员可见。</small>
          </div>
          <el-form label-position="top" @submit.prevent="saveProfile">
            <div class="profile-form-grid">
              <el-form-item label="姓名" required>
                <el-input v-model="form.real_name" maxlength="50" placeholder="请输入姓名" />
              </el-form-item>
              <el-form-item label="邮箱">
                <el-input v-model="form.email" maxlength="100" placeholder="用于联系和账号识别" />
              </el-form-item>
              <el-form-item label="手机号">
                <el-input v-model="form.phone" maxlength="11" placeholder="请输入 11 位手机号" />
              </el-form-item>
              <el-form-item label="用户名">
                <el-input :model-value="profile.username" disabled />
              </el-form-item>
            </div>
            <el-form-item label="个人简介">
              <el-input
                v-model="form.bio"
                type="textarea"
                :rows="5"
                maxlength="500"
                show-word-limit
                placeholder="介绍你的教学方向、学习兴趣或个人经历"
              />
            </el-form-item>
            <div class="profile-save-row">
              <el-button type="primary" native-type="submit" :loading="saving">保存资料</el-button>
            </div>
          </el-form>
        </section>
        <aside class="surface-card profile-privacy-note">
          <strong>主页展示范围</strong>
          <p>他人只能看到头像、姓名、身份、个人简介，以及教师已经发布的课程。</p>
          <p>用户名、邮箱和手机号不会显示在公开主页。</p>
        </aside>
      </div>

      <section v-else class="surface-card public-profile-content">
        <div class="profile-biography">
          <p class="eyebrow">个人简介</p>
          <h2>关于{{ profile.real_name }}</h2>
          <p>{{ profile.bio || (profile.role === 'TEACHER' ? '这位教师暂未填写个人简介。' : '这位用户暂未填写个人简介。') }}</p>
        </div>
        <div v-if="profile.role === 'TEACHER'" class="profile-course-section">
          <div class="profile-section-heading">
            <div><p class="eyebrow">授课课程</p><h2>已发布课程</h2></div>
            <span>{{ profile.courses.length }} 门</span>
          </div>
          <div v-if="profile.courses.length" class="profile-course-grid">
            <RouterLink v-for="item in profile.courses" :key="item.id" :to="`/courses/${item.id}`" class="profile-course-card">
              <span class="profile-course-cover" :style="item.cover_url ? { backgroundImage: `url(${item.cover_url})` } : {}">
                <b v-if="!item.cover_url">{{ item.name.slice(0, 1) }}</b>
              </span>
              <span><small>{{ item.category_name || '通识课程' }}</small><strong>{{ item.name }}</strong><p>{{ item.description || '暂无课程简介' }}</p></span>
            </RouterLink>
          </div>
          <el-empty v-else description="这位教师暂时没有已发布课程" :image-size="72" />
        </div>
      </section>
    </template>

    <el-result v-else-if="errorMessage" icon="error" title="个人主页加载失败" :sub-title="errorMessage">
      <template #extra><el-button type="primary" @click="loadProfile">重新加载</el-button></template>
    </el-result>
  </section>
</template>
