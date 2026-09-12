<script setup>
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import api from '../api/client'
import { useAuthStore } from '../stores/auth'


const auth = useAuthStore()
const loading = ref(false)
const overview = ref({})
const courseStatistics = ref([])
const isTeacher = computed(() => auth.user?.role === 'TEACHER')

const studentMetrics = computed(() => [
  { label: '已加入课程', value: overview.value.joined_courses || 0, unit: '门' },
  { label: '完成视频', value: overview.value.completed_videos || 0, unit: '个' },
  { label: '平均视频进度', value: overview.value.average_video_progress || 0, unit: '%' },
  { label: '累计学习时长', value: formatDuration(overview.value.watch_duration_seconds), unit: '' },
  { label: '已提交作业', value: overview.value.submitted_homeworks || 0, unit: '份' },
  { label: '作业平均得分率', value: overview.value.average_homework_percent || 0, unit: '%' },
  { label: '已完成测验', value: overview.value.completed_exams || 0, unit: '次' },
  { label: '测验平均得分率', value: overview.value.average_exam_percent || 0, unit: '%' },
])

const teacherMetrics = computed(() => [
  { label: '全部课程', value: overview.value.courses || 0, unit: '门' },
  { label: '已发布课程', value: overview.value.published_courses || 0, unit: '门' },
  { label: '活跃学生', value: overview.value.active_students || 0, unit: '人' },
  { label: '可学习视频', value: overview.value.ready_videos || 0, unit: '个' },
  { label: '等待回答', value: overview.value.waiting_questions || 0, unit: '个' },
  { label: '待批改作业', value: overview.value.ungraded_homeworks || 0, unit: '份' },
  { label: '已交卷记录', value: overview.value.submitted_exams || 0, unit: '份' },
])

async function load() {
  loading.value = true
  try {
    const requests = [api.get('/statistics')]
    if (isTeacher.value) requests.push(api.get('/statistics/courses'))
    const [overviewResponse, courseResponse] = await Promise.all(requests)
    overview.value = overviewResponse.data
    courseStatistics.value = courseResponse?.data || []
  } catch (error) {
    ElMessage.error(error.message || '统计数据加载失败')
  } finally {
    loading.value = false
  }
}

function formatDuration(seconds) {
  const minutes = Math.floor(Number(seconds || 0) / 60)
  if (minutes < 60) return minutes + ' 分钟'
  return Math.floor(minutes / 60) + ' 小时 ' + (minutes % 60) + ' 分'
}

function statusLabel(status) {
  return { DRAFT: '草稿', PUBLISHED: '已发布', OFFLINE: '已下架' }[status] || status
}

onMounted(load)
</script>

<template>
  <section class="page-section statistics-page" v-loading="loading">
    <div class="page-heading">
      <div>
        <p class="eyebrow">LEARNING INSIGHTS</p>
        <h1>{{ isTeacher ? '教学数据' : '学习数据' }}</h1>
        <p>{{ isTeacher ? '数据直接由学习、作业和测验记录实时聚合。' : '回顾学习投入与课程任务完成情况。' }}</p>
      </div>
    </div>

    <div class="statistics-grid">
      <article v-for="metric in (isTeacher ? teacherMetrics : studentMetrics)" :key="metric.label">
        <span>{{ metric.label }}</span>
        <div><strong>{{ metric.value }}</strong><small>{{ metric.unit }}</small></div>
      </article>
    </div>

    <div v-if="isTeacher" class="management-surface statistics-table">
      <div class="surface-heading">
        <div><strong>课程表现</strong><span>{{ courseStatistics.length }} 门课程</span></div>
        <small>进度按“活跃学生 × 可学习视频”计算，未观看视频计入 0%</small>
      </div>
      <el-table :data="courseStatistics">
        <el-table-column prop="course_name" label="课程" min-width="190" />
        <el-table-column label="状态" width="100">
          <template #default="scope">{{ statusLabel(scope.row.status) }}</template>
        </el-table-column>
        <el-table-column prop="student_count" label="学生" width="90" />
        <el-table-column prop="ready_video_count" label="视频" width="90" />
        <el-table-column label="平均进度" width="120">
          <template #default="scope">{{ scope.row.average_progress }}%</template>
        </el-table-column>
        <el-table-column label="作业均分率" width="130">
          <template #default="scope">{{ scope.row.average_homework_percent }}%</template>
        </el-table-column>
        <el-table-column label="测验均分率" width="130">
          <template #default="scope">{{ scope.row.average_exam_percent }}%</template>
        </el-table-column>
        <template #empty><el-empty description="暂无课程统计" /></template>
      </el-table>
    </div>
  </section>
</template>
