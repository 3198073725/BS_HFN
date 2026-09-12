<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import api from '../api/client'


const courses = ref([])
const categories = ref([])
const loading = ref(false)
const courseDialog = ref(false)
const chapterDialog = ref(false)
const videoDialog = ref(false)
const selectedCourse = ref(null)
const selectedChapter = ref(null)
const videoFile = ref(null)
const uploading = ref(false)
let disposed = false
const courseForm = reactive({ name: '', category_id: null, description: '', detail: '' })
const chapterForm = reactive({ title: '', description: '', sort_order: 0 })

async function load() {
  loading.value = true
  try {
    const [courseResponse, categoryResponse] = await Promise.all([
      api.get('/courses/mine'),
      api.get('/courses/categories'),
    ])
    courses.value = courseResponse.data
    categories.value = categoryResponse.data
  } catch (error) {
    ElMessage.error(error.message || '教学课程加载失败')
  } finally {
    loading.value = false
  }
}

async function createCourse() {
  try {
    await api.post('/courses', courseForm)
    ElMessage.success('课程创建成功')
    courseDialog.value = false
    Object.assign(courseForm, { name: '', category_id: null, description: '', detail: '' })
    await load()
  } catch (error) {
    ElMessage.error(error.message || '课程创建失败')
  }
}

function openChapter(course) {
  selectedCourse.value = course
  chapterDialog.value = true
}

async function createChapter() {
  try {
    await api.post(`/courses/${selectedCourse.value.id}/chapters`, chapterForm)
    ElMessage.success('章节创建成功')
    chapterDialog.value = false
    Object.assign(chapterForm, { title: '', description: '', sort_order: 0 })
    await load()
  } catch (error) {
    ElMessage.error(error.message || '章节创建失败')
  }
}

function openVideo(chapter) {
  selectedChapter.value = chapter
  videoFile.value = null
  Object.assign(videoForm, { title: '', description: '', sort_order: 0 })
  videoDialog.value = true
}

const videoForm = reactive({ title: '', description: '', sort_order: 0 })

function selectVideoFile(event) {
  videoFile.value = event.target.files?.[0] || null
}

async function uploadVideo() {
  if (!videoFile.value) {
    ElMessage.warning('请选择视频文件')
    return
  }
  const data = new FormData()
  data.append('chapter_id', selectedChapter.value.id)
  data.append('title', videoForm.title)
  data.append('description', videoForm.description)
  data.append('sort_order', videoForm.sort_order)
  data.append('video_file', videoFile.value)
  uploading.value = true
  try {
    const response = await api.post('/videos/upload', data, { timeout: 0 })
    if (response.data.status === 'READY') {
      ElMessage.success('视频处理完成')
      await load()
    } else if (response.data.status === 'FAILED') {
      ElMessage.error(response.data.error_message || '视频处理失败')
      await load()
    } else {
      ElMessage.success('视频已提交后台处理，可继续编辑其他内容')
      await load()
      void monitorVideo(response.data.id)
    }
    videoDialog.value = false
  } catch (error) {
    ElMessage.error(error.message || '视频上传失败')
  } finally {
    uploading.value = false
  }
}

async function monitorVideo(videoId) {
  for (let attempt = 0; attempt < 150 && !disposed; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000))
    if (disposed) return
    try {
      const response = await api.get(`/videos/${videoId}/status`)
      if (response.data.status === 'READY') {
        ElMessage.success(`视频“${response.data.title}”处理完成`)
        await load()
        return
      }
      if (response.data.status === 'FAILED') {
        ElMessage.error(response.data.error_message || '后台视频处理失败')
        await load()
        return
      }
    } catch {
      return
    }
  }
  if (!disposed) ElMessage.warning('视频仍在后台处理，请稍后刷新课程列表')
}

async function publish(course) {
  try {
    await ElMessageBox.confirm('确认发布该课程？课程至少需要一个章节。', '发布课程')
    await api.post(`/courses/${course.id}/publish`)
    ElMessage.success('课程已发布')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '发布失败')
  }
}

onMounted(load)
onBeforeUnmount(() => {
  disposed = true
})
</script>

<template>
  <section>
    <div class="page-heading">
      <div>
        <p class="eyebrow">TEACHER</p>
        <h1>教学管理</h1>
      </div>
      <el-button type="primary" @click="courseDialog = true">创建课程</el-button>
    </div>
    <el-table v-loading="loading" :data="courses" stripe>
      <el-table-column type="expand">
        <template #default="scope">
          <div class="chapter-list">
            <div v-for="chapter in scope.row.chapters" :key="chapter.id" class="chapter-row">
              <div>
                <strong>{{ chapter.title }}</strong>
                <span class="muted"> · {{ chapter.videos.length }} 个视频</span>
                <div v-for="video in chapter.videos" :key="video.id" class="video-status">
                  {{ video.title }} · {{ video.status }}
                </div>
              </div>
              <el-button :disabled="scope.row.status !== 'DRAFT'" @click="openVideo(chapter)">上传视频</el-button>
            </div>
            <el-empty v-if="!scope.row.chapters.length" description="暂无章节" :image-size="64" />
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="课程" min-width="220" />
      <el-table-column prop="category_name" label="分类" width="140" />
      <el-table-column prop="status" label="状态" width="120" />
      <el-table-column label="操作" min-width="220">
        <template #default="scope">
          <el-button :disabled="scope.row.status !== 'DRAFT'" @click="openChapter(scope.row)">添加章节</el-button>
          <el-button type="primary" :disabled="scope.row.status !== 'DRAFT'" @click="publish(scope.row)">
            发布
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="courseDialog" title="创建课程" width="min(560px, 92vw)">
      <el-form :model="courseForm" label-position="top">
        <el-form-item label="课程名称" required><el-input v-model="courseForm.name" /></el-form-item>
        <el-form-item label="课程分类" required>
          <el-select v-model="courseForm.category_id" style="width: 100%">
            <el-option v-for="item in categories" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="简介"><el-input v-model="courseForm.description" /></el-form-item>
        <el-form-item label="详情"><el-input v-model="courseForm.detail" type="textarea" :rows="4" /></el-form-item>
      </el-form>
      <template #footer><el-button type="primary" @click="createCourse">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="chapterDialog" title="添加章节" width="min(520px, 92vw)">
      <el-form :model="chapterForm" label-position="top">
        <el-form-item label="章节标题" required><el-input v-model="chapterForm.title" /></el-form-item>
        <el-form-item label="章节描述"><el-input v-model="chapterForm.description" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="chapterForm.sort_order" :min="0" /></el-form-item>
      </el-form>
      <template #footer><el-button type="primary" @click="createChapter">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="videoDialog" title="上传视频" width="min(520px, 92vw)" :close-on-click-modal="!uploading">
      <el-form :model="videoForm" label-position="top">
        <el-form-item label="视频标题" required><el-input v-model="videoForm.title" /></el-form-item>
        <el-form-item label="视频描述"><el-input v-model="videoForm.description" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="videoForm.sort_order" :min="0" /></el-form-item>
        <el-form-item label="视频文件" required>
          <input
            type="file"
            accept=".mp4,.mov,.mkv,.avi,.webm,video/mp4,video/quicktime,video/x-matroska,video/webm"
            @change="selectVideoFile"
          />
        </el-form-item>
      </el-form>
      <p class="muted">大视频处理需要时间；后台异步模式会在后台完成后提示结果。</p>
      <template #footer>
        <el-button type="primary" :loading="uploading" @click="uploadVideo">上传并处理</el-button>
      </template>
    </el-dialog>
  </section>
</template>
