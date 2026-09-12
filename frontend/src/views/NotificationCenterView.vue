<script setup>
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import api from '../api/client'


const router = useRouter()
const loading = ref(false)
const notifications = ref([])
const unreadOnly = ref(false)
const paging = reactive({ page: 1, page_size: 12, total: 0 })
const unreadCount = ref(0)

async function load() {
  loading.value = true
  try {
    const response = await api.get('/notifications', {
      params: { page: paging.page, page_size: paging.page_size, unread_only: unreadOnly.value },
    })
    notifications.value = response.data.items
    Object.assign(paging, response.data.pagination)
    unreadCount.value = response.data.unread_count
    window.dispatchEvent(new CustomEvent('bs-hfn:notification-count', { detail: unreadCount.value }))
  } catch (error) {
    ElMessage.error(error.message || '通知加载失败')
  } finally {
    loading.value = false
  }
}

async function openNotification(item) {
  if (!item.read) {
    try {
      await api.put(`/notifications/${item.id}/read`)
      item.read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
      window.dispatchEvent(new CustomEvent('bs-hfn:notification-count', { detail: unreadCount.value }))
    } catch (error) {
      ElMessage.error(error.message || '通知状态更新失败')
      return
    }
  }
  if (item.link) await router.push(item.link)
}

async function markAllRead() {
  try {
    await api.put('/notifications/read-all')
    ElMessage.success('全部通知已标记为已读')
    await load()
  } catch (error) {
    ElMessage.error(error.message || '操作失败')
  }
}

function changeFilter() {
  paging.page = 1
  void load()
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
  return { HOMEWORK: '课程作业', EXAM: '在线测验', QUESTION: '课程答疑', SYSTEM: '系统消息' }[value] || value
}

onMounted(load)
</script>

<template>
  <section class="page-section notification-center" v-loading="loading">
    <div class="page-heading">
      <div><p class="eyebrow">站内通知</p><h1>消息中心</h1><p>集中查看作业、测验、答疑和系统状态更新。</p></div>
      <el-button :disabled="unreadCount === 0" @click="markAllRead">全部标为已读</el-button>
    </div>

    <div class="notification-toolbar surface-card">
      <div><strong>{{ unreadCount }}</strong><span>条未读通知</span></div>
      <el-switch v-model="unreadOnly" active-text="只看未读" @change="changeFilter" />
    </div>

    <div class="notification-list surface-card">
      <button
        v-for="item in notifications"
        :key="item.id"
        type="button"
        :class="['notification-item', { unread: !item.read }]"
        @click="openNotification(item)"
      >
        <span class="notification-dot" aria-hidden="true"></span>
        <span class="notification-copy">
          <span><small>{{ categoryLabel(item.category) }}</small><time>{{ formatDate(item.created_at) }}</time></span>
          <strong>{{ item.title }}</strong>
          <p>{{ item.content }}</p>
          <i>发送者：{{ item.sender_name }}<template v-if="item.link"> · 点击查看相关内容</template></i>
        </span>
      </button>
      <el-empty v-if="!loading && !notifications.length" description="暂时没有通知" :image-size="72" />
      <el-pagination
        v-if="paging.total > paging.page_size"
        class="collection-pagination"
        background
        layout="prev, pager, next, total"
        :current-page="paging.page"
        :page-size="paging.page_size"
        :total="paging.total"
        @current-change="changePage"
      />
    </div>
  </section>
</template>
