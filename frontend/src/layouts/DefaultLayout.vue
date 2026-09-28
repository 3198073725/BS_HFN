<script setup>
import { ElMessage } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import api from '../api/client'


const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const loggingOut = ref(false)
const mainNav = ref(null)
const unreadCount = ref(0)
const unreadUnavailable = ref(false)
let unreadSequence = 0
let unreadRequest = null
let unreadTimer = null
let disposed = false
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

async function revealActiveNavigation() {
  await nextTick()
  const navigation = mainNav.value
  if (!navigation || navigation.scrollWidth <= navigation.clientWidth) return
  const activeLink = navigation.querySelector('a.active')
  if (!activeLink) return
  const target = activeLink.offsetLeft - (navigation.clientWidth - activeLink.offsetWidth) / 2
  navigation.scrollTo({ left: Math.max(0, target), behavior: 'smooth' })
}

async function loadUnreadCount() {
  const userId = auth.user?.id
  if (!auth.isAuthenticated) {
    unreadSequence += 1
    unreadCount.value = 0
    unreadUnavailable.value = false
    return
  }
  if (disposed || document.visibilityState === 'hidden' || !navigator.onLine || unreadRequest?.userId === userId) return
  const ticket = { userId, sequence: ++unreadSequence }
  unreadRequest = ticket
  try {
    const response = await api.get('/notifications', { params: { page: 1, page_size: 1, unread_only: true } })
    if (disposed || ticket.sequence !== unreadSequence || auth.user?.id !== userId) return
    unreadCount.value = response.data.unread_count || 0
    unreadUnavailable.value = false
  } catch {
    if (!disposed && ticket.sequence === unreadSequence && auth.user?.id === userId) unreadUnavailable.value = true
  } finally {
    if (unreadRequest === ticket) unreadRequest = null
  }
}

function updateUnreadCount(event) {
  if (!auth.isAuthenticated) return
  unreadSequence += 1
  unreadCount.value = Math.max(0, Number(event.detail || 0))
  unreadUnavailable.value = false
}

watch(() => route.name, () => { revealActiveNavigation(); void loadUnreadCount() })
watch(() => auth.user?.id, () => { unreadCount.value = 0; unreadSequence += 1; void loadUnreadCount() }, { immediate: true })
onMounted(() => {
  revealActiveNavigation()
  window.addEventListener('bs-hfn:notification-count', updateUnreadCount)
  window.addEventListener('focus', loadUnreadCount)
  window.addEventListener('online', loadUnreadCount)
  document.addEventListener('visibilitychange', loadUnreadCount)
  unreadTimer = window.setInterval(loadUnreadCount, 30000)
})
onBeforeUnmount(() => {
  disposed = true
  unreadSequence += 1
  window.clearInterval(unreadTimer)
  window.removeEventListener('bs-hfn:notification-count', updateUnreadCount)
  window.removeEventListener('focus', loadUnreadCount)
  window.removeEventListener('online', loadUnreadCount)
  document.removeEventListener('visibilitychange', loadUnreadCount)
})
</script>

<template>
  <el-container class="app-shell">
    <el-header class="app-header">
      <div class="header-inner">
        <RouterLink class="site-brand" to="/" aria-label="课后辅导教学平台首页">
          <span class="brand-mark">课</span>
          <span class="site-brand-copy">
            <strong>课后辅导教学平台</strong>
            <small>教学与学习管理</small>
          </span>
        </RouterLink>

        <nav ref="mainNav" class="main-nav" aria-label="主导航">
          <RouterLink to="/" :class="{ active: route.name === 'home' }">首页</RouterLink>
          <RouterLink to="/courses" :class="{ active: ['courses', 'course-detail'].includes(route.name) }">
            课程中心
          </RouterLink>
          <RouterLink
            v-if="auth.user?.role === 'STUDENT'"
            to="/learning"
            :class="{ active: route.name === 'learning' }"
          >
            我的学习
          </RouterLink>
          <RouterLink
            v-if="auth.isAuthenticated"
            to="/notifications"
            :title="unreadUnavailable ? '网络异常，未读数量可能尚未更新' : '查看站内消息'"
            :class="{ active: route.name === 'notifications' }"
          >
            消息<span v-if="unreadCount" class="nav-unread-count">{{ unreadCount > 99 ? '99+' : unreadCount }}</span>
          </RouterLink>
          <RouterLink
            v-if="['STUDENT', 'TEACHER'].includes(auth.user?.role)"
            to="/classes"
            :class="{ active: route.name === 'classes' }"
          >
            {{ auth.user?.role === 'TEACHER' ? '班级管理' : '我的班级' }}
          </RouterLink>
          <RouterLink
            v-if="['STUDENT', 'TEACHER'].includes(auth.user?.role)"
            to="/homeworks"
            :class="{ active: route.name === 'homeworks' }"
          >
            {{ auth.user?.role === 'TEACHER' ? '作业管理' : '课程作业' }}
          </RouterLink>
          <RouterLink
            v-if="['STUDENT', 'TEACHER'].includes(auth.user?.role)"
            to="/exams"
            :class="{ active: route.name === 'exams' }"
          >
            {{ auth.user?.role === 'TEACHER' ? '测验管理' : '在线测验' }}
          </RouterLink>
          <RouterLink
            v-if="auth.user?.role === 'TEACHER'"
            to="/teacher/courses"
            :class="{ active: route.name === 'teacher-courses' }"
          >
            教学管理
          </RouterLink>
          <RouterLink
            v-if="auth.user?.role === 'TEACHER'"
            to="/teacher/questions"
            :class="{ active: route.name === 'teacher-questions' }"
          >
            课程答疑
          </RouterLink>
          <RouterLink
            v-if="['STUDENT', 'TEACHER'].includes(auth.user?.role)"
            to="/statistics"
            :class="{ active: route.name === 'statistics' }"
          >
            数据概览
          </RouterLink>
          <RouterLink
            v-if="auth.user?.role === 'ADMIN'"
            to="/admin"
            :class="{ active: route.name === 'admin-dashboard' }"
          >
            系统后台
          </RouterLink>
        </nav>

        <div class="session-actions">
          <RouterLink
            v-if="auth.user"
            class="user-chip"
            :class="{ active: route.name === 'my-profile' }"
            to="/profile"
            title="查看并编辑个人主页"
            aria-label="查看并编辑个人主页"
          >
            <span class="user-avatar">
              <img v-if="auth.user.avatar_url" :src="auth.user.avatar_url" alt="" />
              <template v-else>{{ (auth.user.real_name || auth.user.username || '用').slice(0, 1) }}</template>
            </span>
            <span class="user-copy">
              <strong>{{ auth.user.real_name || auth.user.username }}</strong>
              <small>{{ roleLabel }}</small>
            </span>
          </RouterLink>
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
        <span>课后辅导教学平台</span>
        <span>课程学习与教学管理服务</span>
      </div>
    </footer>
  </el-container>
</template>
