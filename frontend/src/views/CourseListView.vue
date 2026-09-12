<script setup>
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import api from '../api/client'


const categories = ref([])
const courses = ref([])
const categoryId = ref(null)
const loading = ref(false)
const currentPage = ref(1)
const pageSize = 9
let requestSequence = 0

const pagedCourses = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return courses.value.slice(start, start + pageSize)
})

async function load() {
  const requestId = ++requestSequence
  const selectedCategoryId = categoryId.value
  loading.value = true
  try {
    const [categoryResponse, courseResponse] = await Promise.all([
      api.get('/courses/categories'),
      api.get('/courses', { params: selectedCategoryId ? { category_id: selectedCategoryId } : {} }),
    ])
    if (requestId !== requestSequence) return
    categories.value = categoryResponse.data
    courses.value = courseResponse.data
  } catch (error) {
    if (requestId === requestSequence) ElMessage.error(error.message || '课程加载失败')
  } finally {
    if (requestId === requestSequence) loading.value = false
  }
}

watch(categoryId, () => {
  currentPage.value = 1
  load()
})
onMounted(load)
</script>

<template>
  <section class="page-section">
    <div class="page-heading">
      <div>
        <p class="eyebrow">课程资源</p>
        <h1>发现适合你的课程</h1>
        <p>浏览已发布课程，按分类快速筛选学习内容。</p>
      </div>
      <div class="filter-control">
        <span>课程分类</span>
        <el-select v-model="categoryId" clearable placeholder="全部分类">
          <el-option v-for="item in categories" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </div>
    </div>

    <div class="course-result-meta">
      <span>{{ loading ? '正在加载课程…' : `共 ${courses.length} 门课程` }}</span>
      <i></i>
    </div>

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
          <p class="course-teacher">授课教师 · {{ course.teacher_name || '待更新' }}</p>
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
        description="该分类下暂无已发布课程"
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
  </section>
</template>
