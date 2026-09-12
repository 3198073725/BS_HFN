<script setup>
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import api from '../api/client'
import VideoPlayer from '../components/VideoPlayer.vue'


const route = useRoute()
const course = ref(null)
const loading = ref(false)
const errorMessage = ref('')
const selectedVideo = ref(null)

async function loadCourse() {
  loading.value = true
  errorMessage.value = ''
  try {
    course.value = (await api.get(`/courses/${route.params.id}`)).data
    selectedVideo.value = course.value.chapters
      .flatMap((chapter) => chapter.videos)
      .find((video) => video.status === 'READY') || null
  } catch (error) {
    errorMessage.value = error.message || '课程加载失败'
    ElMessage.error(errorMessage.value)
  } finally {
    loading.value = false
  }
}

function readyVideos(chapter) {
  return chapter.videos.filter((video) => video.status === 'READY')
}

onMounted(loadCourse)
</script>

<template>
  <section class="page-section course-detail-page" v-loading="loading">
    <template v-if="course">
      <RouterLink class="breadcrumb-link" to="/courses">← 返回课程中心</RouterLink>

      <header class="course-detail-hero">
        <div>
          <div class="course-detail-meta">
            <span>{{ course.category_name || '通识课程' }}</span>
            <i></i>
            <span>已发布</span>
          </div>
          <h1>{{ course.name }}</h1>
          <p>{{ course.description || '教师暂未填写课程简介。' }}</p>
          <div class="teacher-line">
            <span class="teacher-avatar">{{ course.teacher_name?.slice(0, 1) || '师' }}</span>
            <span><small>授课教师</small><strong>{{ course.teacher_name || '待更新' }}</strong></span>
          </div>
        </div>
        <div class="course-detail-mark" aria-hidden="true">{{ course.name?.slice(0, 1) || '课' }}</div>
      </header>

      <div class="learning-layout">
        <section class="player-panel">
          <div class="panel-heading">
            <div>
              <p class="eyebrow">NOW PLAYING</p>
              <h2>{{ selectedVideo?.title || '选择一个视频开始学习' }}</h2>
            </div>
            <span v-if="selectedVideo" class="playing-status"><i></i> 可播放</span>
          </div>
          <VideoPlayer v-if="selectedVideo" :source="selectedVideo.hls_url" />
          <div v-else class="player-placeholder">
            <span>▶</span>
            <strong>暂无可播放视频</strong>
            <p>课程视频准备好视频后会显示在这里。</p>
          </div>
        </section>

        <aside class="chapter-panel">
          <div class="panel-heading compact">
            <div>
              <p class="eyebrow">CONTENTS</p>
              <h2>课程章节</h2>
            </div>
            <span>{{ course.chapters.length }} 章</span>
          </div>
          <div v-if="course.chapters.length" class="chapter-stack">
            <section v-for="(chapter, chapterIndex) in course.chapters" :key="chapter.id" class="chapter-card">
              <div class="chapter-heading">
                <span>{{ String(chapterIndex + 1).padStart(2, '0') }}</span>
                <div>
                  <strong>{{ chapter.title }}</strong>
                  <small>{{ chapter.description || '暂无章节简介' }}</small>
                </div>
              </div>
              <div v-if="readyVideos(chapter).length" class="video-list">
                <button
                  v-for="video in readyVideos(chapter)"
                  :key="video.id"
                  type="button"
                  :class="{ active: selectedVideo?.id === video.id }"
                  @click="selectedVideo = video"
                >
                  <span>{{ selectedVideo?.id === video.id ? '▶' : '▷' }}</span>
                  <strong>{{ video.title }}</strong>
                </button>
              </div>
              <p v-else class="chapter-empty">本章暂无可播放视频</p>
            </section>
          </div>
          <el-empty v-else description="暂无课程章节" :image-size="72" />
        </aside>
      </div>
    </template>

    <el-result v-else-if="errorMessage" icon="error" title="课程加载失败" :sub-title="errorMessage">
      <template #extra>
        <el-button type="primary" @click="loadCourse">重新加载</el-button>
      </template>
    </el-result>
  </section>
</template>
