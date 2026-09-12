<script setup>
import { ElMessage } from 'element-plus'
import { onMounted, ref, watch } from 'vue'

import api from '../api/client'


const categories = ref([])
const courses = ref([])
const categoryId = ref(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const [categoryResponse, courseResponse] = await Promise.all([
      api.get('/courses/categories'),
      api.get('/courses', { params: categoryId.value ? { category_id: categoryId.value } : {} }),
    ])
    categories.value = categoryResponse.data
    courses.value = courseResponse.data
  } catch (error) {
    ElMessage.error(error.message || '课程加载失败')
  } finally {
    loading.value = false
  }
}

watch(categoryId, load)
onMounted(load)
</script>

<template>
  <section>
    <div class="page-heading">
      <div>
        <p class="eyebrow">COURSE</p>
        <h1>已发布课程</h1>
      </div>
      <el-select v-model="categoryId" clearable placeholder="全部分类" style="width: 180px">
        <el-option v-for="item in categories" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
    </div>

    <el-table v-if="courses.length" v-loading="loading" :data="courses" stripe>
      <el-table-column prop="name" label="课程名称" min-width="220">
        <template #default="scope">
          <RouterLink class="table-link" :to="`/courses/${scope.row.id}`">{{ scope.row.name }}</RouterLink>
        </template>
      </el-table-column>
      <el-table-column prop="category_name" label="分类" width="140" />
      <el-table-column prop="teacher_name" label="授课教师" width="150" />
      <el-table-column prop="description" label="简介" min-width="260" show-overflow-tooltip />
      <el-table-column label="状态" width="110">
        <template #default><el-tag type="success">已发布</el-tag></template>
      </el-table-column>
    </el-table>
    <el-empty v-else v-loading="loading" description="暂无已发布课程" />
  </section>
</template>
