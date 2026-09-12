<script setup>
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import api from '../api/client'
import VideoPlayer from '../components/VideoPlayer.vue'


const route = useRoute()
const course = ref(null)
const loading = ref(false)
const selectedVideo = ref(null)

onMounted(async () => {
  loading.value = true
  try {
    course.value = (await api.get(`/courses/${route.params.id}`)).data
  } catch (error) {
    ElMessage.error(error.message || '课程加载失败')
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section v-loading="loading">
    <template v-if="course">
      <p class="eyebrow">{{ course.category_name }}</p>
      <h1>{{ course.name }}</h1>
      <p class="muted">授课教师：{{ course.teacher_name }}</p>
      <p>{{ course.description }}</p>
      <el-divider />
      <h2>课程章节</h2>
      <VideoPlayer v-if="selectedVideo" :source="selectedVideo.hls_url" />
      <el-timeline v-if="course.chapters.length">
        <el-timeline-item v-for="chapter in course.chapters" :key="chapter.id">
          <strong>{{ chapter.title }}</strong>
          <p class="muted">{{ chapter.description || '暂无章节简介' }}</p>
          <el-button
            v-for="video in chapter.videos.filter((item) => item.status === 'READY')"
            :key="video.id"
            text
            type="primary"
            @click="selectedVideo = video"
          >
            ▶ {{ video.title }}
          </el-button>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无章节" />
    </template>
  </section>
</template>
