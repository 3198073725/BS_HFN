<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api/client'
import { useDialogFocus } from '../utils/dialogFocus'

const route = useRoute()
const notices = ref([])
const loading = ref(false)
const loadError = ref('')
const page = ref(1)
const pageSize = 8
const selectedNotice = ref(null)
const detailVisible = ref(false)
const restoreDetailFocus = useDialogFocus(detailVisible)
const pagedNotices = computed(() => notices.value.slice((page.value - 1) * pageSize, page.value * pageSize))
let requestSequence = 0

function revealLinkedNotice() {
  if (loading.value) return
  const id = Number(route.query.notice_id)
  if (!id) return
  const notice = notices.value.find((item) => item.id === id)
  if (notice) { selectedNotice.value = notice; detailVisible.value = true }
  else ElMessage.info('该公告不存在或已下线')
}

async function load() {
  const requestId = ++requestSequence
  loading.value = true
  loadError.value = ''
  try {
    const response = await api.get('/notices')
    if (requestId !== requestSequence) return
    notices.value = response.data
    page.value = Math.min(page.value, Math.max(1, Math.ceil(notices.value.length / pageSize)))
  } catch (error) {
    if (requestId !== requestSequence) return
    loadError.value = error.message || '公告加载失败'
  } finally { if (requestId === requestSequence) loading.value = false }
  if (requestId === requestSequence && !loadError.value) revealLinkedNotice()
}

function formatDate(value) {
  if (!value) return '—'
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  return new Date(normalized).toLocaleString('zh-CN', { hour12: false })
}

watch(() => route.query.notice_id, revealLinkedNotice)
onMounted(load)
onBeforeUnmount(() => { requestSequence += 1 })
</script>

<template>
  <section class="page-section notice-list-page" v-loading="loading">
    <div class="page-heading">
      <div><p class="eyebrow">平台公告</p><h1>通知公告</h1><p>查看平台已经发布的公告与完整说明。</p></div>
      <RouterLink class="action-link compact-action" to="/">返回首页</RouterLink>
    </div>
    <el-result v-if="loadError" icon="error" title="公告加载失败" :sub-title="loadError">
      <template #extra><el-button @click="load">重新加载</el-button></template>
    </el-result>
    <div
      v-else
      class="public-notice-list surface-card stable-pagination-shell notice-pagination-shell"
      :class="{ 'has-pagination': notices.length > pageSize }"
    >
      <div class="public-notice-items stable-pagination-body">
      <article v-for="notice in pagedNotices" :key="notice.id">
        <time>{{ formatDate(notice.publish_time) }}</time>
        <h2>{{ notice.title }}</h2>
        <p>{{ notice.content }}</p>
        <el-button @click="selectedNotice = notice; detailVisible = true">阅读全文</el-button>
      </article>
      <el-empty v-if="!loading && !notices.length" description="当前没有已发布公告" :image-size="72" />
      </div>
      <el-pagination v-if="notices.length > pageSize" v-model:current-page="page" class="collection-pagination" background
        layout="prev, pager, next" :page-size="pageSize" :total="notices.length" aria-label="公告分页" />
    </div>
    <el-dialog v-model="detailVisible" :title="selectedNotice?.title" width="min(720px, 94vw)" @close-auto-focus="restoreDetailFocus">
      <small>{{ formatDate(selectedNotice?.publish_time) }}</small>
      <p class="task-full-description">{{ selectedNotice?.content }}</p>
      <template #footer><el-button @click="detailVisible = false">关闭</el-button></template>
    </el-dialog>
  </section>
</template>
