<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'

import api from '../api/client'


const loading = ref(false)
const activeTab = ref('courses')
const courses = ref([])
const favorites = ref([])

async function load() {
  loading.value = true
  try {
    const [courseResponse, favoriteResponse] = await Promise.all([
      api.get('/learning/courses'),
      api.get('/learning/favorites'),
    ])
    courses.value = courseResponse.data
    favorites.value = favoriteResponse.data
  } catch (error) {
    ElMessage.error(error.message || '学习中心加载失败')
  } finally {
    loading.value = false
  }
}

async function leaveCourse(course) {
  try {
    await ElMessageBox.confirm(
      '退出后将停止保存新的学习进度，已有记录、笔记和提问会保留。',
      '退出课程',
      { type: 'warning', confirmButtonText: '确认退出' },
    )
    await api.delete(`/learning/courses/${course.id}/join`)
    courses.value = courses.value.filter((item) => item.id !== course.id)
    ElMessage.success('已退出课程')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '退出课程失败')
  }
}

async function removeFavorite(course) {
  try {
    await api.delete(`/learning/courses/${course.id}/favorite`)
    favorites.value = favorites.value.filter((item) => item.id !== course.id)
    ElMessage.success('已取消收藏')
  } catch (error) {
    ElMessage.error(error.message || '取消收藏失败')
  }
}

function formatDate(value) {
  if (!value) return '最近加入'
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(new Date(value))
}

onMounted(load)
</script>

<template>
  <section class="page-section learning-center" v-loading="loading">
    <div class="page-heading">
      <div>
        <p class="eyebrow">MY LEARNING</p>
        <h1>我的学习</h1>
        <p>继续上次的进度，集中查看已加入和收藏的课程。</p>
      </div>
      <RouterLink class="action-link action-link-primary compact-action" to="/courses">发现更多课程</RouterLink>
    </div>

    <div class="learning-summary">
      <article>
        <span>已加入课程</span>
        <strong>{{ courses.length }}</strong>
        <small>门</small>
      </article>
      <article>
        <span>已收藏课程</span>
        <strong>{{ favorites.length }}</strong>
        <small>门</small>
      </article>
      <article>
        <span>已完成课程</span>
        <strong>{{ courses.filter((item) => item.learning_progress >= 90).length }}</strong>
        <small>门</small>
      </article>
    </div>

    <div class="study-tabs center-tabs" role="tablist">
      <button :class="{ active: activeTab === 'courses' }" type="button" @click="activeTab = 'courses'">
        已加入 <span>{{ courses.length }}</span>
      </button>
      <button :class="{ active: activeTab === 'favorites' }" type="button" @click="activeTab = 'favorites'">
        我的收藏 <span>{{ favorites.length }}</span>
      </button>
    </div>

    <div v-if="activeTab === 'courses'" class="learning-course-grid">
      <article v-for="course in courses" :key="course.id" class="learning-course-card">
        <div class="learning-card-mark">{{ course.name?.slice(0, 1) || '课' }}</div>
        <div class="learning-card-content">
          <div class="learning-card-meta">
            <span>{{ course.category_name || '通识课程' }}</span>
            <small>{{ formatDate(course.join_time) }}加入</small>
          </div>
          <h2>{{ course.name }}</h2>
          <p>{{ course.description || '教师暂未填写课程简介。' }}</p>
          <div class="progress-line">
            <div><i :style="{ width: `${course.learning_progress}%` }"></i></div>
            <span>{{ course.learning_progress }}%</span>
          </div>
          <div class="learning-card-actions">
            <RouterLink :to="`/courses/${course.id}`">继续学习 →</RouterLink>
            <button type="button" @click="leaveCourse(course)">退出课程</button>
          </div>
        </div>
      </article>
      <el-empty
        v-if="!loading && !courses.length"
        class="surface-card learning-empty"
        description="还没有加入课程，先去课程中心看看吧"
      />
    </div>

    <div v-else class="learning-course-grid">
      <article v-for="course in favorites" :key="course.id" class="learning-course-card favorite-card">
        <div class="learning-card-mark">{{ course.name?.slice(0, 1) || '课' }}</div>
        <div class="learning-card-content">
          <div class="learning-card-meta">
            <span>{{ course.category_name || '通识课程' }}</span>
            <small>★ 已收藏</small>
          </div>
          <h2>{{ course.name }}</h2>
          <p>{{ course.description || '教师暂未填写课程简介。' }}</p>
          <div class="learning-card-actions">
            <RouterLink :to="`/courses/${course.id}`">查看课程 →</RouterLink>
            <button type="button" @click="removeFavorite(course)">取消收藏</button>
          </div>
        </div>
      </article>
      <el-empty
        v-if="!loading && !favorites.length"
        class="surface-card learning-empty"
        description="还没有收藏课程"
      />
    </div>
  </section>
</template>
