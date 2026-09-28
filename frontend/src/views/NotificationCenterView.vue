<script setup>
import { ElMessage } from 'element-plus'
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '../api/client'
import { focusElement } from '../utils/dialogFocus'


const router = useRouter()
const loading = ref(false)
const loadError = ref('')
const readingId = ref(null)
const markingAll = ref(false)
const notifications = ref([])
const unreadOnly = ref(false)
const paging = reactive({ page: 1, page_size: 12, total: 0 })
const unreadCount = ref(0)
let requestSequence = 0
let disposed = false

async function restoreActionFocus(opener, path, index = 0, id = null) {
  await nextTick()
  if (disposed || router.currentRoute.value.fullPath !== path) return
  // Do not steal focus if the user moved to another control while waiting.
  if (document.activeElement !== document.body && document.activeElement !== opener) return
  if (focusElement(opener)) return
  const rows = [...document.querySelectorAll('.notification-item')]
  const target = rows.find((row) => row.dataset.notificationId === String(id)) || rows[Math.min(index, rows.length - 1)]
  if (focusElement(target)) return
  focusElement(document.querySelector('.notification-toolbar [role="switch"]'))
}

async function load() {
  if (disposed) return
  const requestId = ++requestSequence
  loading.value = true
  loadError.value = ''
  try {
    const response = await api.get('/notifications', {
      params: { page: paging.page, page_size: paging.page_size, unread_only: unreadOnly.value },
    })
    if (requestId !== requestSequence) return
    notifications.value = response.data.items
    Object.assign(paging, response.data.pagination)
    unreadCount.value = response.data.unread_count
    window.dispatchEvent(new CustomEvent('bs-hfn:notification-count', { detail: unreadCount.value }))
  } catch (error) {
    if (requestId !== requestSequence) return
    loadError.value = error.message || '通知加载失败'
    ElMessage.error(loadError.value)
  } finally {
    if (requestId === requestSequence) loading.value = false
  }
}

async function openNotification(item) {
  if (readingId.value !== null || markingAll.value || loading.value) return
  const opener = document.activeElement
  const path = router.currentRoute.value.fullPath
  const index = notifications.value.findIndex((row) => row.id === item.id)
  readingId.value = item.id
  const requestId = requestSequence
  try {
    if (!item.read) {
      await api.put(`/notifications/${item.id}/read`)
      if (requestId !== requestSequence) return
      item.read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
      window.dispatchEvent(new CustomEvent('bs-hfn:notification-count', { detail: unreadCount.value }))
      if (unreadOnly.value) {
        paging.page = Math.min(paging.page, Math.max(1, Math.ceil((paging.total - 1) / paging.page_size)))
        await load()
      }
    }
    if (item.link) await router.push(item.link)
  } catch (error) {
    if (requestId === requestSequence) ElMessage.error(error.message || '通知状态更新失败')
  } finally {
    readingId.value = null
    await restoreActionFocus(opener, path, index, item.id)
  }
}

async function markAllRead() {
  if (markingAll.value || readingId.value !== null || loading.value) return
  const opener = document.activeElement
  const path = router.currentRoute.value.fullPath
  markingAll.value = true
  try {
    await api.put('/notifications/read-all')
    if (disposed) return
    ElMessage.success('全部通知已标记为已读')
    if (unreadOnly.value) paging.page = 1
    await load()
  } catch (error) {
    if (!disposed) ElMessage.error(error.message || '操作失败')
  } finally {
    markingAll.value = false
    await restoreActionFocus(opener, path)
  }
}

function changeFilter() {
  paging.page = 1
  void load()
}

function toggleUnreadWithKeyboard(event) {
  if (event.repeat || readingId.value !== null || markingAll.value) return
  // Avoid the switch's cancelled native click reverting only input.checked.
  unreadOnly.value = !unreadOnly.value
  changeFilter()
}

function changePage(page) {
  paging.page = page
  void load()
}

function formatDate(value) {
  if (!value) return '—'
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }).format(new Date(normalized))
}

function categoryLabel(value) {
  return { HOMEWORK: '课程作业', EXAM: '在线测验', QUESTION: '课程答疑', PASSWORD: '账号安全', CLASS: '班级通知', SYSTEM: '系统消息' }[value] || value
}

onMounted(load)
onBeforeUnmount(() => { disposed = true; requestSequence += 1 })
</script>

<template>
  <section class="page-section notification-center" v-loading="loading">
    <div class="page-heading">
      <div><p class="eyebrow">站内通知</p><h1>消息中心</h1><p>集中查看作业、测验、答疑和系统状态更新。</p></div>
      <el-button :disabled="unreadCount === 0 || loading || readingId !== null" :loading="markingAll" @click="markAllRead">全部标为已读</el-button>
    </div>

    <div class="notification-toolbar surface-card">
      <div><strong>{{ unreadCount }}</strong><span>条未读通知</span></div>
      <el-switch v-model="unreadOnly" :disabled="readingId !== null || markingAll" active-text="只看未读" aria-label="只看未读" @change="changeFilter" @keydown.space.prevent="toggleUnreadWithKeyboard" />
    </div>

    <div
      class="notification-list surface-card stable-pagination-shell notification-pagination-shell"
      :class="{ 'has-pagination': paging.total > paging.page_size }"
    >
      <el-result v-if="loadError" icon="error" title="通知加载失败" :sub-title="loadError">
        <template #extra><el-button @click="load">重新加载</el-button></template>
      </el-result>
      <template v-else>
      <div class="notification-items stable-pagination-body">
      <button
        v-for="item in notifications"
        :key="item.id"
        :data-notification-id="item.id"
        type="button"
        :disabled="readingId !== null || markingAll || loading"
        :aria-busy="readingId === item.id"
        :class="['notification-item', { unread: !item.read }]"
        @click="openNotification(item)"
      >
        <span class="notification-dot" aria-hidden="true"></span>
        <span class="notification-copy">
          <span><small>{{ categoryLabel(item.category) }}</small><time>{{ formatDate(item.created_at) }}</time></span>
          <strong>{{ item.title }}</strong>
          <p>{{ item.content }}</p>
          <i>发送者：{{ item.sender_name }}<template v-if="readingId === item.id"> · 正在打开…</template><template v-else-if="item.link"> · 点击查看相关内容</template></i>
        </span>
      </button>
      <el-empty v-if="!loading && !notifications.length" description="暂时没有通知" :image-size="72" />
      </div>
      <el-pagination
        v-if="paging.total > paging.page_size"
        class="collection-pagination"
        background
        :disabled="readingId !== null || markingAll || loading"
        layout="prev, pager, next, total"
        :current-page="paging.page"
        :page-size="paging.page_size"
        :total="paging.total"
        @current-change="changePage"
      />
      </template>
    </div>
  </section>
</template>
