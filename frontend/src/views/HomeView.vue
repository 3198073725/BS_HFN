<script setup>
import { onMounted, ref } from 'vue'

import api from '../api/client'
import { useAuthStore } from '../stores/auth'


const auth = useAuthStore()
const notices = ref([])
const noticesLoading = ref(false)
const noticesError = ref('')

async function loadNotices() {
  noticesLoading.value = true
  noticesError.value = ''
  try {
    const response = await api.get('/notices')
    notices.value = response.data.slice(0, 4)
  } catch (error) {
    noticesError.value = error.message || '公告加载失败'
  } finally {
    noticesLoading.value = false
  }
}

function formatDate(value) {
  if (!value) return ''
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? value : value + 'Z'
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(new Date(normalized))
}

onMounted(loadNotices)
</script>

<template>
  <div class="portal-home">
    <section class="portal-welcome" aria-labelledby="portal-title">
      <div class="portal-welcome-copy">
        <p class="portal-kicker">课后辅导教学平台</p>
        <h1 id="portal-title">欢迎使用课后辅导教学平台</h1>
        <p>面向学生、教师和教学管理人员，提供课程学习、班级管理、作业测验与课程答疑等服务。</p>
        <div class="portal-actions">
          <RouterLink class="portal-button portal-button-primary" to="/courses">进入课程中心</RouterLink>
          <RouterLink v-if="!auth.isAuthenticated" class="portal-button" to="/login">账号登录</RouterLink>
          <RouterLink v-else-if="auth.user?.role === 'TEACHER'" class="portal-button" to="/teacher/courses">进入教学管理</RouterLink>
          <RouterLink v-else-if="auth.user?.role === 'STUDENT'" class="portal-button" to="/learning">进入我的学习</RouterLink>
          <RouterLink v-else-if="auth.user?.role === 'ADMIN'" class="portal-button" to="/admin">进入系统后台</RouterLink>
        </div>
      </div>

      <aside class="portal-service-card" aria-label="平台服务说明">
        <div class="portal-card-heading"><h2>平台服务</h2><span>教学服务</span></div>
        <dl>
          <div><dt>课程资源</dt><dd>按课程和章节统一管理</dd></div>
          <div><dt>视频学习</dt><dd>支持电脑与移动端播放</dd></div>
          <div><dt>教学活动</dt><dd>作业、测验与答疑集中处理</dd></div>
        </dl>
      </aside>
    </section>

    <section class="portal-workbench" aria-label="平台常用内容">
      <div class="portal-main-column">
        <div class="portal-section-heading">
          <div><h2>常用功能</h2><p>根据当前身份进入对应的学习或管理页面</p></div>
        </div>
        <div class="portal-shortcuts">
          <RouterLink to="/courses"><span>课</span><div><strong>课程中心</strong><small>浏览已发布课程和章节内容</small></div></RouterLink>
          <RouterLink v-if="auth.user?.role === 'STUDENT'" to="/learning"><span>学</span><div><strong>我的学习</strong><small>查看已加入课程与学习进度</small></div></RouterLink>
          <RouterLink v-if="['STUDENT', 'TEACHER'].includes(auth.user?.role)" to="/classes">
            <span>班</span><div><strong>{{ auth.user?.role === 'TEACHER' ? '班级管理' : '我的班级' }}</strong><small>查看班级与成员信息</small></div>
          </RouterLink>
          <RouterLink v-if="['STUDENT', 'TEACHER'].includes(auth.user?.role)" to="/homeworks">
            <span>作</span><div><strong>{{ auth.user?.role === 'TEACHER' ? '作业管理' : '课程作业' }}</strong><small>发布、提交和批阅课程作业</small></div>
          </RouterLink>
          <RouterLink v-if="['STUDENT', 'TEACHER'].includes(auth.user?.role)" to="/exams">
            <span>测</span><div><strong>{{ auth.user?.role === 'TEACHER' ? '测验管理' : '在线测验' }}</strong><small>组织测验并查看成绩</small></div>
          </RouterLink>
          <RouterLink v-if="auth.user?.role === 'TEACHER'" to="/teacher/questions"><span>答</span><div><strong>课程答疑</strong><small>集中回复学生课程问题</small></div></RouterLink>
          <RouterLink v-if="auth.user?.role === 'ADMIN'" to="/admin"><span>管</span><div><strong>系统后台</strong><small>管理账号、分类和系统公告</small></div></RouterLink>
          <RouterLink v-if="!auth.isAuthenticated" to="/register"><span>注</span><div><strong>学生注册</strong><small>创建学生账号并开始学习</small></div></RouterLink>
          <RouterLink v-if="!auth.isAuthenticated" to="/login"><span>登</span><div><strong>统一登录</strong><small>学生、教师与管理员账号入口</small></div></RouterLink>
        </div>

        <div class="portal-guide">
          <div class="portal-section-heading"><div><h2>使用说明</h2><p>首次使用可按照以下顺序开始</p></div></div>
          <ol>
            <li><span>1</span><div><strong>登录平台</strong><p>使用用户名、邮箱、学号或工号登录。</p></div></li>
            <li><span>2</span><div><strong>选择课程</strong><p>在课程中心查看课程简介和章节安排。</p></div></li>
            <li><span>3</span><div><strong>完成学习任务</strong><p>按要求观看视频、提交作业并参加测验。</p></div></li>
          </ol>
        </div>
      </div>

      <aside class="portal-notices" aria-labelledby="notice-title" v-loading="noticesLoading">
        <div class="portal-card-heading"><h2 id="notice-title">通知公告</h2><RouterLink class="portal-notice-link" to="/notices">全部公告</RouterLink></div>
        <div v-if="noticesError" class="portal-notice-empty">
          <p>{{ noticesError }}</p><el-button @click="loadNotices">重新加载</el-button>
        </div>
        <div v-else-if="notices.length" class="portal-notice-list">
          <article v-for="notice in notices" :key="notice.id">
            <time>{{ formatDate(notice.publish_time) }}</time>
            <div><h3><RouterLink :to="`/notices?notice_id=${notice.id}`">{{ notice.title }}</RouterLink></h3><p>{{ notice.content }}</p><RouterLink class="portal-notice-link" :to="`/notices?notice_id=${notice.id}`">阅读全文</RouterLink></div>
          </article>
        </div>
        <div v-else-if="!noticesLoading" class="portal-notice-empty">当前没有新的系统公告</div>
      </aside>
    </section>
  </div>
</template>
