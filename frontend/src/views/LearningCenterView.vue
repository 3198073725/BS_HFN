<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import api from '../api/client'
import CourseThumbnail from '../components/CourseThumbnail.vue'


const loading = ref(false)
const loadError = ref('')
const activeTab = ref('courses')
const courses = ref([])
const favorites = ref([])
const currentPage = ref(1)
const pageSize = 8
const pendingAction = ref('')
let requestSequence = 0
let disposed = false

function navigateTabs(event) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  activeTab.value = event.key === 'Home' ? 'courses' : event.key === 'End' ? 'favorites'
    : activeTab.value === 'courses' ? 'favorites' : 'courses'
  event.currentTarget.parentElement.querySelector(`#learning-tab-${activeTab.value}`)?.focus()
}

const pagedCourses = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return courses.value.slice(start, start + pageSize)
})
const pagedFavorites = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return favorites.value.slice(start, start + pageSize)
})

async function load() {
  const requestId = ++requestSequence
  loading.value = true
  loadError.value = ''
  try {
    const [courseResponse, favoriteResponse] = await Promise.all([
      api.get('/learning/courses'),
      api.get('/learning/favorites'),
    ])
    if (requestId !== requestSequence || disposed) return
    courses.value = courseResponse.data
    favorites.value = favoriteResponse.data
  } catch (error) {
    if (requestId !== requestSequence || disposed) return
    loadError.value = error.message || '学习中心加载失败'
    ElMessage.error(error.message || '学习中心加载失败')
  } finally {
    if (requestId === requestSequence && !disposed) loading.value = false
  }
}

async function leaveCourse(course) {
  if (pendingAction.value || loading.value) return
  pendingAction.value = `leave:${course.id}`
  try {
    await ElMessageBox.confirm(
      '退出后将停止保存新的学习进度，已有记录、笔记和提问会保留。',
      '退出课程',
      { type: 'warning', confirmButtonText: '确认退出' },
    )
    if (disposed) return
    await api.delete(`/learning/courses/${course.id}/join`)
    if (disposed) return
    courses.value = courses.value.filter((item) => item.id !== course.id)
    ElMessage.success('已退出课程')
  } catch (error) {
    if (!disposed && error !== 'cancel' && error !== 'close') ElMessage.error(error.message || '退出课程失败')
  } finally {
    pendingAction.value = ''
  }
}

async function removeFavorite(course) {
  if (pendingAction.value || loading.value) return
  pendingAction.value = `favorite:${course.id}`
  try {
    await api.delete(`/learning/courses/${course.id}/favorite`)
    if (disposed) return
    favorites.value = favorites.value.filter((item) => item.id !== course.id)
    ElMessage.success('已取消收藏')
  } catch (error) {
    if (!disposed) ElMessage.error(error.message || '取消收藏失败')
  } finally {
    pendingAction.value = ''
  }
}

function formatDate(value) {
  if (!value) return '最近加入'
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(new Date(value))
}

watch(activeTab, () => {
  currentPage.value = 1
})
watch([() => courses.value.length, () => favorites.value.length], () => {
  const total = activeTab.value === 'courses' ? courses.value.length : favorites.value.length
  currentPage.value = Math.min(currentPage.value, Math.max(1, Math.ceil(total / pageSize)))
})
onMounted(load)
onBeforeUnmount(() => { disposed = true; requestSequence += 1 })
</script>

<template>
  <section class="page-section learning-center" v-loading="loading">
    <div class="page-heading">
      <div>
        <p class="eyebrow">学习中心</p>
        <h1>我的学习</h1>
        <p>继续上次的进度，集中查看已加入和收藏的课程。</p>
      </div>
      <RouterLink class="action-link action-link-primary compact-action" to="/courses">发现更多课程</RouterLink>
    </div>

    <el-result v-if="loadError" icon="error" title="学习中心加载失败" :sub-title="loadError">
      <template #extra><el-button @click="load">重新加载</el-button></template>
    </el-result>
    <template v-else>
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

    <div class="study-tabs center-tabs" role="tablist" aria-label="学习课程分类">
      <button id="learning-tab-courses" role="tab" aria-controls="learning-panel-courses" :aria-selected="activeTab === 'courses'" :tabindex="activeTab === 'courses' ? 0 : -1" :class="{ active: activeTab === 'courses' }" type="button" @keydown="navigateTabs" @click="activeTab = 'courses'">
        已加入 <span>{{ courses.length }}</span>
      </button>
      <button id="learning-tab-favorites" role="tab" aria-controls="learning-panel-favorites" :aria-selected="activeTab === 'favorites'" :tabindex="activeTab === 'favorites' ? 0 : -1" :class="{ active: activeTab === 'favorites' }" type="button" @keydown="navigateTabs" @click="activeTab = 'favorites'">
        我的收藏 <span>{{ favorites.length }}</span>
      </button>
    </div>

    <div
      v-show="activeTab === 'courses'"
      id="learning-panel-courses"
      role="tabpanel"
      aria-labelledby="learning-tab-courses"
      class="stable-pagination-shell learning-pagination-shell"
      :class="{ 'has-pagination': courses.length > pageSize }"
    >
      <template v-if="activeTab === 'courses'">
      <div class="learning-course-grid stable-pagination-body">
      <article v-for="course in pagedCourses" :key="course.id" class="learning-course-card">
        <CourseThumbnail class="learning-card-mark" :src="course.cover_url || ''" :name="course.name" />
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
            <button type="button" :disabled="!!pendingAction || loading" @click="leaveCourse(course)">{{ pendingAction === `leave:${course.id}` ? '正在退出…' : '退出课程' }}</button>
          </div>
        </div>
      </article>
      <el-empty
        v-if="!loading && !courses.length"
        class="surface-card learning-empty"
        description="还没有加入课程，先去课程中心看看吧"
      />
      </div>
      <el-pagination
        v-if="courses.length > pageSize"
        v-model:current-page="currentPage"
        class="collection-pagination"
        background
        layout="prev, pager, next"
        :page-size="pageSize"
        :total="courses.length"
        aria-label="已加入课程分页"
      />
      </template>
    </div>

    <div
      v-show="activeTab === 'favorites'"
      id="learning-panel-favorites"
      role="tabpanel"
      aria-labelledby="learning-tab-favorites"
      class="stable-pagination-shell learning-pagination-shell"
      :class="{ 'has-pagination': favorites.length > pageSize }"
    >
      <template v-if="activeTab === 'favorites'">
      <div class="learning-course-grid stable-pagination-body">
      <article v-for="course in pagedFavorites" :key="course.id" class="learning-course-card favorite-card">
        <CourseThumbnail class="learning-card-mark" :src="course.cover_url || ''" :name="course.name" />
        <div class="learning-card-content">
          <div class="learning-card-meta">
            <span>{{ course.category_name || '通识课程' }}</span>
            <small>★ 已收藏</small>
          </div>
          <h2>{{ course.name }}</h2>
          <p>{{ course.description || '教师暂未填写课程简介。' }}</p>
          <div class="learning-card-actions">
            <RouterLink :to="`/courses/${course.id}`">查看课程 →</RouterLink>
            <button type="button" :disabled="!!pendingAction || loading" @click="removeFavorite(course)">{{ pendingAction === `favorite:${course.id}` ? '正在取消…' : '取消收藏' }}</button>
          </div>
        </div>
      </article>
      <el-empty
        v-if="!loading && !favorites.length"
        class="surface-card learning-empty"
        description="还没有收藏课程"
      />
      </div>
      <el-pagination
        v-if="favorites.length > pageSize"
        v-model:current-page="currentPage"
        class="collection-pagination"
        background
        layout="prev, pager, next"
        :page-size="pageSize"
        :total="favorites.length"
        aria-label="收藏课程分页"
      />
      </template>
    </div>
    </template>
  </section>
</template>

<style scoped>
.learning-center .learning-course-card { grid-template-columns: 156px minmax(0, 1fr); }
.learning-center .learning-card-mark { width: 100%; height: auto; min-height: 0; aspect-ratio: 16 / 10; align-self: center; }
@media (max-width: 600px) {
  .learning-center .learning-course-card { grid-template-columns: 94px minmax(0, 1fr); }
}
</style>
