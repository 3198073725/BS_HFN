<script setup>
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import api from '../api/client'
import StatisticsChart from '../components/StatisticsChart.vue'
import OverflowText from '../components/OverflowText.vue'
import { useAuthStore } from '../stores/auth'


const auth = useAuthStore()
const loading = ref(false)
const loadError = ref('')
const overview = ref({})
const courseStatistics = ref([])
const isTeacher = computed(() => auth.user?.role === 'TEACHER')
let disposed = false
let requestSequence = 0
const studentPercentRows = computed(() => [
  { label: '平均视频进度', values: [overview.value.average_video_progress] },
  { label: '作业平均得分率', values: [overview.value.average_homework_percent] },
  { label: '测验平均得分率', values: [overview.value.average_exam_percent] },
])
const studentCountRows = computed(() => [
  { label: '已有学习记录', values: [overview.value.learned_videos] },
  { label: '完成视频', values: [overview.value.completed_videos] },
  { label: '已提交作业', values: [overview.value.submitted_homeworks] },
  { label: '已批改作业', values: [overview.value.graded_homeworks] },
  { label: '已完成测验', values: [overview.value.completed_exams] },
])
const coursePercentRows = computed(() => courseStatistics.value.map((course) => ({
  label: course.course_name, values: [course.average_progress, course.average_homework_percent, course.average_exam_percent],
})))
const courseCountRows = computed(() => ['PUBLISHED', 'DRAFT', 'OFFLINE'].map((status) => ({
  label: statusLabel(status), values: [courseStatistics.value.filter((course) => course.status === status).length],
})))

const studentMetrics = computed(() => [
  { label: '在册课程（含下线）', value: overview.value.joined_courses || 0, unit: '门' },
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
  { label: '在册学生', value: overview.value.active_students || 0, unit: '人' },
  { label: '就绪视频（含下线）', value: overview.value.ready_videos || 0, unit: '个' },
  { label: '等待回答', value: overview.value.waiting_questions || 0, unit: '个' },
  { label: '待批改作业', value: overview.value.ungraded_homeworks || 0, unit: '份' },
  { label: '已交卷记录', value: overview.value.submitted_exams || 0, unit: '份' },
])

async function load() {
  const requestId = ++requestSequence
  loading.value = true
  loadError.value = ''
  try {
    const requests = [api.get('/statistics')]
    if (isTeacher.value) requests.push(api.get('/statistics/courses'))
    const [overviewResponse, courseResponse] = await Promise.all(requests)
    if (disposed || requestId !== requestSequence) return
    overview.value = overviewResponse.data
    courseStatistics.value = courseResponse?.data || []
  } catch (error) {
    if (disposed || requestId !== requestSequence) return
    loadError.value = error.message || '统计数据加载失败'
    ElMessage.error(error.message || '统计数据加载失败')
  } finally {
    if (!disposed && requestId === requestSequence) loading.value = false
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
onBeforeUnmount(() => { disposed = true; requestSequence += 1 })
</script>

<template>
  <section class="page-section statistics-page" v-loading="loading">
    <div class="page-heading">
      <div>
        <p class="eyebrow">数据概览</p>
        <h1>{{ isTeacher ? '教学数据' : '学习数据' }}</h1>
        <p>{{ isTeacher ? '数据直接由学习、作业和测验记录实时聚合。' : '回顾学习投入与课程任务完成情况。' }}</p>
      </div>
      <el-button :loading="loading" :disabled="loading" @click="load">刷新数据</el-button>
    </div>

    <el-result v-if="loadError" icon="error" title="统计数据加载失败" :sub-title="loadError">
      <template #extra><el-button @click="load">重新加载</el-button></template>
    </el-result>
    <template v-else>
    <p class="dialog-tip">{{ isTeacher
      ? '总览包含所有课程及历史待办；课程表现按当前在册学生统计，作业与测验只计已发布或已关闭任务，均分只计已评分记录。下线不清除历史数据。'
      : `当前可学习课程 ${overview.published_joined_courses || 0} 门；在册课程包含已下线课程，其余学习时长、完成与成绩指标为累计记录，包含退出或下线课程的历史数据。` }}</p>
    <div class="statistics-grid">
      <article v-for="metric in (isTeacher ? teacherMetrics : studentMetrics)" :key="metric.label">
        <span>{{ metric.label }}</span>
        <div><strong>{{ metric.value }}</strong><small>{{ metric.unit }}</small></div>
      </article>
    </div>

    <div v-if="!loading" class="statistics-charts">
      <template v-if="isTeacher">
        <StatisticsChart title="课程学习与成绩对比" caption="当前在册学生的平均视频进度、作业与测验得分率；每页最多6门课程，完整名称见数据表。无评分记录的均分沿用接口返回0。"
          :rows="coursePercentRows" :series="['视频进度', '作业得分率', '测验得分率']" percentage />
        <StatisticsChart title="课程发布状态" caption="统计全部课程，包括草稿和已下线课程，不受图表分页影响。"
          :rows="courseCountRows" :series="['课程数量']" unit="门" />
      </template>
      <template v-else>
        <StatisticsChart title="学习与成绩概览" caption="进度与得分率分别统计，不代表作业提交率；无评分记录时沿用接口返回0。"
          :rows="studentPercentRows" :series="['百分比']" percentage />
        <StatisticsChart title="累计学习与任务记录" caption="视频按个数、作业按份数、测验按次数统计，各项独立计数，不相加。包含累计历史记录。"
          :rows="studentCountRows" :series="['记录数量']" />
      </template>
    </div>

    <div v-if="isTeacher" class="management-surface statistics-table">
      <div class="surface-heading">
        <div><strong>课程表现</strong><span>{{ courseStatistics.length }} 门课程</span></div>
        <small>进度按“当前在册学生 × 就绪视频”计算；下线课程保留历史表现，未观看计入0%</small>
      </div>
      <el-table :data="courseStatistics" max-height="520">
        <el-table-column prop="course_name" label="课程" min-width="190"><template #default="scope"><OverflowText :text="scope.row.course_name" label="查看统计课程名称全文" /></template></el-table-column>
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
    </template>
  </section>
</template>

<style scoped>
.statistics-charts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; margin-top: 24px; align-items: start; }
@media (max-width: 900px) { .statistics-charts { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 600px) {
  .statistics-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
  .statistics-grid article { min-width: 0; }
  .statistics-grid article > span { min-height: 34px; }
  .statistics-grid article > div { flex-wrap: wrap; }
  .statistics-grid strong { font-size: 22px; overflow-wrap: anywhere; }
}
</style>
