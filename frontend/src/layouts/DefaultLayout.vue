<script setup>
import { ElMessage } from 'element-plus'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'


const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const loggingOut = ref(false)
const roleLabel = computed(() => ({
  ADMIN: '管理员',
  TEACHER: '教师',
  STUDENT: '学生',
})[auth.user?.role] || '用户')

async function handleLogout() {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await auth.logout()
    ElMessage.success('已安全退出')
  } catch (error) {
    ElMessage.warning(error.message || '本地会话已清除，但服务器会话清理失败')
  } finally {
    loggingOut.value = false
  }
  await router.replace('/')
}
</script>

<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <div class="header-inner">
        <RouterLink class="site-brand" to="/" aria-label="课后辅导系统首页">
          <span class="brand-mark">辅</span>
          <span class="site-brand-copy">
            <strong>课后辅导</strong>
            <small>BS_HFN</small>
          </span>
        </RouterLink>

        <nav class="main-nav" aria-label="主导航">
          <RouterLink to="/" :class="{ active: route.name === 'home' }">首页</RouterLink>
          <RouterLink to="/courses" :class="{ active: ['courses', 'course-detail'].includes(route.name) }">
            课程中心
          </RouterLink>
          <RouterLink
            v-if="auth.user?.role === 'TEACHER'"
            to="/teacher/courses"
            :class="{ active: route.name === 'teacher-courses' }"
          >
            教学管理
          </RouterLink>
        </nav>

        <div class="session-actions">
          <div v-if="auth.user" class="user-chip">
            <span class="user-avatar">{{ (auth.user.real_name || auth.user.username || '用').slice(0, 1) }}</span>
            <span class="user-copy">
              <strong>{{ auth.user.real_name || auth.user.username }}</strong>
              <small>{{ roleLabel }}</small>
            </span>
          </div>
          <button
            v-if="auth.isAuthenticated"
            class="header-action"
            type="button"
            :disabled="loggingOut"
            @click="handleLogout"
          >
            {{ loggingOut ? '退出中' : '退出' }}
          </button>
          <RouterLink v-else class="header-login" to="/login">登录</RouterLink>
        </div>
      </div>
    </el-header>
    <el-main class="app-main">
      <RouterView />
    </el-main>
    <footer class="app-footer">
      <div>
        <span>BS_HFN 课后辅导系统</span>
        <span>Web · FFmpeg · HLS</span>
      </div>
    </footer>
  </el-container>
</template>
