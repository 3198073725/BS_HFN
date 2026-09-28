<script setup>
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import api from '../api/client'


const categories = ref([])
const teachers = ref([])
const courses = ref([])
const categoryId = ref(null)
const teacherId = ref(null)
const keywordInput = ref('')
const keyword = ref('')
const loading = ref(false)
const loadError = ref('')
const currentPage = ref(1)
const pageSize = 9
let requestSequence = 0

const pagedCourses = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return courses.value.slice(start, start + pageSize)
})
const hasActiveFilters = computed(() => Boolean(categoryId.value || teacherId.value || keyword.value))

async function load() {
  const requestId = ++requestSequence
  const selectedCategoryId = categoryId.value
  const selectedTeacherId = teacherId.value
  const selectedKeyword = keyword.value
  loading.value = true
  loadError.value = ''
  try {
    const params = {}
    if (selectedCategoryId) params.category_id = selectedCategoryId
    if (selectedTeacherId) params.teacher_id = selectedTeacherId
    if (selectedKeyword) params.keyword = selectedKeyword
    const [categoryResponse, teacherResponse, courseResponse] = await Promise.all([
      api.get('/courses/categories'),
      api.get('/courses/teachers'),
      api.get('/courses', { params }),
    ])
    if (requestId !== requestSequence) return
    categories.value = categoryResponse.data
    teachers.value = teacherResponse.data
    courses.value = courseResponse.data
    currentPage.value = Math.min(currentPage.value, Math.max(1, Math.ceil(courses.value.length / pageSize)))
  } catch (error) {
    if (requestId === requestSequence) {
      loadError.value = error.message || '课程加载失败'
      ElMessage.error(loadError.value)
    }
  } finally {
    if (requestId === requestSequence) loading.value = false
  }
}

function applyKeyword() {
  const nextKeyword = keywordInput.value.trim()
  if (keyword.value === nextKeyword) {
    currentPage.value = 1
    load()
    return
  }
  keyword.value = nextKeyword
  currentPage.value = 1
  load()
}

function resetFilters() {
  const selectionChanged = categoryId.value !== null || teacherId.value !== null
  categoryId.value = null
  teacherId.value = null
  keywordInput.value = ''
  keyword.value = ''
  currentPage.value = 1
  if (!selectionChanged) load()
}

watch([categoryId, teacherId], () => {
  currentPage.value = 1
  load()
})
onMounted(load)
onBeforeUnmount(() => { requestSequence += 1 })
</script>

<template>
  <section class="page-section">
    <div class="page-heading">
      <div>
        <p class="eyebrow">课程资源</p>
        <h1>发现适合你的课程</h1>
        <p>按课程名称、课程分类和授课老师查找公开课程。</p>
      </div>
    </div>

    <div class="course-filter-panel" aria-label="课程筛选条件">
      <div class="course-filter-field">
        <span>课程分类</span>
        <el-select
          v-model="categoryId"
          clearable
          placeholder="全部分类"
          aria-label="课程分类"
          popper-class="course-filter-dropdown"
        >
          <el-option v-for="item in categories" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </div>
      <div class="course-filter-field">
        <span>授课老师</span>
        <el-select
          v-model="teacherId"
          clearable
          filterable
          placeholder="全部老师"
          aria-label="授课老师"
          popper-class="course-filter-dropdown"
        >
          <el-option v-for="item in teachers" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </div>
      <div class="course-filter-field course-keyword-field">
        <span>课程关键词</span>
        <el-input
          v-model="keywordInput"
          clearable
          maxlength="100"
          placeholder="搜索课程名称或简介"
          aria-label="课程关键词"
          @clear="applyKeyword"
          @keyup.enter="applyKeyword"
        />
      </div>
      <div class="course-filter-actions">
        <el-button type="primary" :loading="loading" @click="applyKeyword">查询</el-button>
        <el-button :disabled="!hasActiveFilters && !keywordInput" @click="resetFilters">重置</el-button>
      </div>
    </div>

    <el-result v-if="loadError" icon="error" title="课程列表加载失败" :sub-title="loadError">
      <template #extra><el-button @click="load">重新加载</el-button></template>
    </el-result>
    <template v-else>
    <div class="course-result-meta">
      <span>{{ loading ? '正在加载课程…' : `${hasActiveFilters ? '当前条件下' : ''}共 ${courses.length} 门课程` }}</span>
      <i></i>
    </div>

    <div class="course-pagination-shell">
    <div class="course-grid" v-loading="loading">
      <article
        v-for="(course, index) in pagedCourses"
        :key="course.id"
        class="course-card"
        :class="`course-accent-${index % 3}`"
      >
        <div
          class="course-cover"
          :class="{ 'has-image': course.cover_url }"
          :style="course.cover_url ? { backgroundImage: `url(&quot;${course.cover_url}&quot;)` } : null"
        >
          <span class="course-category">{{ course.category_name || '通识课程' }}</span>
          <span v-if="!course.cover_url" class="course-monogram">{{ course.name?.slice(0, 1) || '课' }}</span>
          <span class="course-state"><i></i> 已发布</span>
        </div>
        <div class="course-card-body">
          <p class="course-teacher">
            授课教师 ·
            <RouterLink v-if="course.teacher_id" :to="`/users/${course.teacher_id}`">
              {{ course.teacher_name || '待更新' }}
            </RouterLink>
            <span v-else>{{ course.teacher_name || '待更新' }}</span>
          </p>
          <h2>
            <RouterLink :to="`/courses/${course.id}`">{{ course.name }}</RouterLink>
          </h2>
          <p class="course-description">{{ course.description || '教师暂未填写课程简介。' }}</p>
          <RouterLink class="course-open" :to="`/courses/${course.id}`">
            查看课程 <span aria-hidden="true">→</span>
          </RouterLink>
        </div>
      </article>
      <el-empty
        v-if="!loading && !courses.length"
        class="surface-card course-empty"
        :description="hasActiveFilters ? '没有符合当前筛选条件的课程' : '暂无已发布课程'"
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
      aria-label="课程列表分页"
    />
    </div>
    </template>
  </section>
</template>
