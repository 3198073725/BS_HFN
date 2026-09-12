<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import api from '../api/client'


const courses = ref([])
const categories = ref([])
const loading = ref(false)
const courseFormRef = ref(null)
const chapterFormRef = ref(null)
const videoFormRef = ref(null)
const courseDialog = ref(false)
const chapterDialog = ref(false)
const videoDialog = ref(false)
const selectedCourse = ref(null)
const selectedChapter = ref(null)
const editingCourseId = ref(null)
const editingCourseStatus = ref(null)
const editingChapterId = ref(null)
const videoFile = ref(null)
const videoInputKey = ref(0)
const courseCoverFile = ref(null)
const courseCoverPreview = ref('')
const existingCourseCover = ref('')
const removeExistingCover = ref(false)
const courseCoverInputKey = ref(0)
const uploading = ref(false)
const savingCourse = ref(false)
const savingChapter = ref(false)
let disposed = false
const courseForm = reactive({ name: '', category_id: null, description: '', detail: '' })
const chapterForm = reactive({ title: '', description: '', sort_order: 0 })
const courseRules = {
  name: [
    { required: true, message: '请输入课程名称', trigger: 'blur' },
    { max: 100, message: '课程名称不能超过 100 位', trigger: 'blur' },
  ],
  category_id: [{ required: true, message: '请选择课程分类', trigger: 'change' }],
  description: [{ max: 500, message: '课程简介不能超过 500 位', trigger: 'blur' }],
  detail: [{ max: 10000, message: '课程详情不能超过 10000 位', trigger: 'blur' }],
}
const chapterRules = {
  title: [
    { required: true, message: '请输入章节标题', trigger: 'blur' },
    { max: 150, message: '章节标题不能超过 150 位', trigger: 'blur' },
  ],
  description: [{ max: 500, message: '章节描述不能超过 500 位', trigger: 'blur' }],
}

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

function openCourse(course = null) {
  releaseCourseCoverPreview()
  editingCourseId.value = course?.id || null
  editingCourseStatus.value = course?.status || null
  existingCourseCover.value = course?.cover_url || ''
  courseCoverPreview.value = existingCourseCover.value
  courseCoverFile.value = null
  removeExistingCover.value = false
  courseCoverInputKey.value += 1
  Object.assign(courseForm, {
    name: course?.name || '',
    category_id: course?.category_id || null,
    description: course?.description || '',
    detail: course?.detail || '',
  })
  courseFormRef.value?.clearValidate()
  courseDialog.value = true
}

function resetCourseForm() {
  releaseCourseCoverPreview()
  editingCourseId.value = null
  editingCourseStatus.value = null
  courseCoverFile.value = null
  courseCoverPreview.value = ''
  existingCourseCover.value = ''
  removeExistingCover.value = false
  courseCoverInputKey.value += 1
  Object.assign(courseForm, { name: '', category_id: null, description: '', detail: '' })
  courseFormRef.value?.clearValidate()
}

function releaseCourseCoverPreview() {
  if (courseCoverPreview.value?.startsWith('blob:')) {
    URL.revokeObjectURL(courseCoverPreview.value)
  }
}

function selectCourseCover(event) {
  const file = event.target.files?.[0]
  if (!file) return
  const allowedTypes = ['image/jpeg', 'image/png', 'image/webp']
  if (!allowedTypes.includes(file.type)) {
    releaseCourseCoverPreview()
    courseCoverFile.value = null
    courseCoverPreview.value = existingCourseCover.value
    removeExistingCover.value = false
    ElMessage.warning('课程封面仅支持 JPG、PNG 或 WebP 格式')
    courseCoverInputKey.value += 1
    return
  }
  if (file.size > 5 * 1024 * 1024) {
    releaseCourseCoverPreview()
    courseCoverFile.value = null
    courseCoverPreview.value = existingCourseCover.value
    removeExistingCover.value = false
    ElMessage.warning('课程封面不能超过 5MB')
    courseCoverInputKey.value += 1
    return
  }
  releaseCourseCoverPreview()
  courseCoverFile.value = file
  courseCoverPreview.value = URL.createObjectURL(file)
  removeExistingCover.value = false
}

function clearCourseCover() {
  releaseCourseCoverPreview()
  courseCoverFile.value = null
  courseCoverPreview.value = ''
  removeExistingCover.value = Boolean(existingCourseCover.value)
  courseCoverInputKey.value += 1
}

async function saveCourse() {
  const valid = await courseFormRef.value?.validate().catch(() => false)
  if (!valid || savingCourse.value) return

  const payload = {
    name: courseForm.name,
    category_id: courseForm.category_id,
    description: courseForm.description,
    detail: courseForm.detail,
  }
  const wasNewCourse = !editingCourseId.value
  savingCourse.value = true
  try {
    let courseId = editingCourseId.value
    if (editingCourseId.value) {
      await api.put(`/courses/${editingCourseId.value}`, payload)
    } else {
      const response = await api.post('/courses', payload)
      courseId = response.data.id
      editingCourseId.value = courseId
      editingCourseStatus.value = response.data.status
    }

    try {
      if (courseCoverFile.value) {
        const coverData = new FormData()
        coverData.append('cover', courseCoverFile.value)
        await api.post(`/courses/${courseId}/cover`, coverData)
      } else if (removeExistingCover.value) {
        await api.delete(`/courses/${courseId}/cover`)
      }
    } catch (error) {
      await load()
      ElMessage.error(
        wasNewCourse
          ? `课程已创建，但封面保存失败：${error.message || '请重新选择图片后重试'}`
          : error.message || '课程信息已保存，但封面更新失败',
      )
      return
    }

    ElMessage.success(wasNewCourse ? '课程创建成功' : '课程信息已更新')
    courseDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(error.message || '课程保存失败')
  } finally {
    savingCourse.value = false
  }
}

function openChapter(course, chapter = null) {
  selectedCourse.value = course
  editingChapterId.value = chapter?.id || null
  Object.assign(chapterForm, {
    title: chapter?.title || '',
    description: chapter?.description || '',
    sort_order: chapter?.sort_order || 0,
  })
  chapterFormRef.value?.clearValidate()
  chapterDialog.value = true
}

function resetChapterForm() {
  editingChapterId.value = null
  Object.assign(chapterForm, { title: '', description: '', sort_order: 0 })
  chapterFormRef.value?.clearValidate()
}

async function saveChapter() {
  const valid = await chapterFormRef.value?.validate().catch(() => false)
  if (!valid || savingChapter.value) return

  savingChapter.value = true
  try {
    if (editingChapterId.value) {
      await api.put(
        `/courses/${selectedCourse.value.id}/chapters/${editingChapterId.value}`,
        chapterForm,
      )
      ElMessage.success('章节信息已更新')
    } else {
      await api.post(`/courses/${selectedCourse.value.id}/chapters`, chapterForm)
      ElMessage.success('章节创建成功')
    }
    chapterDialog.value = false
    await load()
  } catch (error) {
    ElMessage.error(error.message || '章节保存失败')
  } finally {
    savingChapter.value = false
  }
}

function openVideo(chapter) {
  selectedChapter.value = chapter
  videoFile.value = null
  Object.assign(videoForm, { title: '', description: '', sort_order: 0 })
  videoInputKey.value += 1
  videoFormRef.value?.clearValidate()
  videoDialog.value = true
}

const videoForm = reactive({ title: '', description: '', sort_order: 0 })
const videoRules = {
  title: [
    { required: true, message: '请输入视频标题', trigger: 'blur' },
    { max: 150, message: '视频标题不能超过 150 位', trigger: 'blur' },
  ],
  description: [{ max: 500, message: '视频描述不能超过 500 位', trigger: 'blur' }],
}

const statusLabels = {
  DRAFT: '草稿',
  PUBLISHED: '已发布',
  OFFLINE: '已下线',
  PENDING: '等待处理',
  PROCESSING: '处理中',
  READY: '可播放',
  FAILED: '处理失败',
}

function statusLabel(status) {
  return statusLabels[status] || status
}

function canMaintain(course) {
  return ['DRAFT', 'PUBLISHED', 'OFFLINE'].includes(course.status)
}

function canDeleteChapter(course) {
  return ['DRAFT', 'OFFLINE'].includes(course.status)
}

function selectVideoFile(event) {
  videoFile.value = event.target.files?.[0] || null
}

async function uploadVideo() {
  const valid = await videoFormRef.value?.validate().catch(() => false)
  if (!valid || uploading.value) return

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
  let consecutiveErrors = 0
  for (let attempt = 0; attempt < 150 && !disposed; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000))
    if (disposed) return
    try {
      const response = await api.get(`/videos/${videoId}/status`)
      consecutiveErrors = 0
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
      consecutiveErrors += 1
      if (consecutiveErrors >= 3) {
        ElMessage.warning('暂时无法获取视频处理状态，请稍后刷新课程列表')
        return
      }
    }
  }
  if (!disposed) ElMessage.warning('视频仍在后台处理，请稍后刷新课程列表')
}

async function publish(course) {
  try {
    const restoring = course.status === 'OFFLINE'
    await ElMessageBox.confirm(
      restoring ? '确认重新发布该课程？' : '确认发布该课程？课程至少需要一个章节。',
      restoring ? '重新发布课程' : '发布课程',
    )
    await api.post(`/courses/${course.id}/publish`)
    ElMessage.success(restoring ? '课程已重新发布' : '课程已发布')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '发布失败')
  }
}

async function offline(course) {
  try {
    await ElMessageBox.confirm('下线后学生暂时无法访问该课程，确认继续？', '下线课程', {
      type: 'warning',
    })
    await api.post(`/courses/${course.id}/offline`)
    ElMessage.success('课程已下线，现在可以编辑内容或重新发布')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '课程下线失败')
  }
}

async function removeCourse(course) {
  try {
    await ElMessageBox.confirm('删除后课程、章节和视频记录将无法恢复，确认继续？', '删除课程', {
      type: 'warning',
    })
    await api.delete(`/courses/${course.id}`)
    ElMessage.success('课程草稿已删除')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '课程删除失败')
  }
}

async function removeChapter(course, chapter) {
  try {
    await ElMessageBox.confirm('删除章节会同时移除其中的视频，确认继续？', '删除章节', {
      type: 'warning',
    })
    await api.delete(`/courses/${course.id}/chapters/${chapter.id}`)
    ElMessage.success('章节已删除')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '章节删除失败')
  }
}

onMounted(load)
onBeforeUnmount(() => {
  disposed = true
  releaseCourseCoverPreview()
})
</script>

<template>
  <section class="page-section teacher-page">
    <div class="page-heading">
      <div>
        <p class="eyebrow">教师工作台</p>
        <h1>教学管理</h1>
        <p>创建课程、组织章节并上传视频；已发布课程下线后可继续编辑。</p>
      </div>
      <el-button type="primary" size="large" @click="openCourse()">＋ 创建课程</el-button>
    </div>

    <div class="management-surface">
      <div class="surface-heading">
        <div>
          <strong>我的课程</strong>
          <span>{{ courses.length }} 门课程</span>
        </div>
        <small>展开课程可查看章节与视频</small>
      </div>
      <p class="table-scroll-hint">左右滑动表格可查看课程状态和全部操作</p>
      <el-table v-loading="loading" :data="courses" max-height="560">
        <el-table-column type="expand">
          <template #default="scope">
            <div class="chapter-list">
              <p v-if="scope.row.status === 'OFFLINE'" class="offline-maintenance-tip">
                课程已下线，可安全调整课程信息、章节和视频，完成后再重新发布。
              </p>
              <div v-for="(chapter, index) in scope.row.chapters" :key="chapter.id" class="chapter-row">
                <div class="chapter-summary">
                  <span class="chapter-number">{{ String(index + 1).padStart(2, '0') }}</span>
                  <div>
                    <strong>{{ chapter.title }}</strong>
                    <span class="muted"> · {{ chapter.videos.length }} 个视频</span>
                    <div v-for="video in chapter.videos" :key="video.id" class="video-status">
                      <span :class="`video-state state-${video.status.toLowerCase()}`"></span>
                      {{ video.title }} · {{ statusLabel(video.status) }}
                    </div>
                  </div>
                </div>
                <div class="chapter-actions">
                  <el-button
                    v-if="canMaintain(scope.row)"
                    link
                    type="primary"
                    @click="openChapter(scope.row, chapter)"
                  >编辑</el-button>
                  <el-button
                    v-if="canDeleteChapter(scope.row)"
                    link
                    type="danger"
                    @click="removeChapter(scope.row, chapter)"
                  >删除</el-button>
                  <el-button :disabled="!canMaintain(scope.row)" @click="openVideo(chapter)">上传视频</el-button>
                </div>
              </div>
              <el-empty v-if="!scope.row.chapters.length" description="暂无章节，先添加第一个章节吧" :image-size="64" />
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="课程" min-width="220">
          <template #default="scope">
            <div class="teacher-course-name">
              <div
                class="teacher-course-cover"
                :class="{ 'has-image': scope.row.cover_url }"
                :style="scope.row.cover_url ? { backgroundImage: `url(&quot;${scope.row.cover_url}&quot;)` } : null"
                aria-hidden="true"
              >{{ scope.row.cover_url ? '' : (scope.row.name?.slice(0, 1) || '课') }}</div>
              <strong class="course-name-cell">{{ scope.row.name }}</strong>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="category_name" label="分类" width="140" />
        <el-table-column label="状态" width="120">
          <template #default="scope">
            <span :class="`course-status status-${scope.row.status.toLowerCase()}`">
              {{ statusLabel(scope.row.status) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="310">
          <template #default="scope">
            <div class="course-row-actions">
              <el-button v-if="canMaintain(scope.row)" link type="primary" @click="openCourse(scope.row)">编辑</el-button>
              <el-button v-if="canMaintain(scope.row)" link @click="openChapter(scope.row)">添加章节</el-button>
              <el-button
                v-if="['DRAFT', 'OFFLINE'].includes(scope.row.status)"
                link
                type="primary"
                @click="publish(scope.row)"
              >{{ scope.row.status === 'OFFLINE' ? '重新发布' : '发布课程' }}</el-button>
              <el-button v-if="scope.row.status === 'PUBLISHED'" link type="warning" @click="offline(scope.row)">下线</el-button>
              <el-button v-if="scope.row.status === 'DRAFT'" link type="danger" @click="removeCourse(scope.row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="还没有课程，点击右上角创建第一门课程" />
        </template>
      </el-table>
    </div>

    <el-dialog
      v-model="courseDialog"
      :title="editingCourseId ? '编辑课程' : '创建课程'"
      width="min(560px, 92vw)"
      :close-on-click-modal="!savingCourse"
      :close-on-press-escape="!savingCourse"
      :show-close="!savingCourse"
      @closed="resetCourseForm"
    >
      <p v-if="editingCourseStatus === 'PUBLISHED'" class="live-maintenance-tip">
        当前课程正在发布中，保存后的课程资料会立即对学生生效。
      </p>
      <el-form ref="courseFormRef" :model="courseForm" :rules="courseRules" label-position="top">
        <el-form-item label="课程名称" prop="name">
          <el-input v-model.trim="courseForm.name" placeholder="例如：高等数学基础" />
        </el-form-item>
        <el-form-item label="课程分类" prop="category_id">
          <el-select v-model="courseForm.category_id" placeholder="请选择课程分类" style="width: 100%">
            <el-option v-for="item in categories" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="课程封面">
          <div class="course-cover-editor">
            <div
              class="course-cover-preview"
              :class="{ 'has-image': courseCoverPreview }"
              :style="courseCoverPreview ? { backgroundImage: `url(&quot;${courseCoverPreview}&quot;)` } : null"
            >
              <span v-if="!courseCoverPreview">{{ courseForm.name?.slice(0, 1) || '课' }}</span>
            </div>
            <div class="course-cover-controls">
              <p>建议使用 16:9 横图，支持 JPG、PNG、WebP，文件不超过 5MB。</p>
              <div>
                <label class="file-select-button">
                  {{ courseCoverPreview ? '更换图片' : '选择图片' }}
                  <input
                    :key="courseCoverInputKey"
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    @change="selectCourseCover"
                  />
                </label>
                <button
                  v-if="courseCoverPreview"
                  class="cover-remove-button"
                  type="button"
                  @click="clearCourseCover"
                >移除封面</button>
              </div>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="课程简介" prop="description">
          <el-input
            v-model.trim="courseForm.description"
            maxlength="500"
            show-word-limit
            placeholder="一句话介绍课程内容"
          />
        </el-form-item>
        <el-form-item label="课程详情" prop="detail">
          <el-input
            v-model.trim="courseForm.detail"
            type="textarea"
            :rows="4"
            maxlength="10000"
            show-word-limit
            placeholder="填写课程目标与适合人群"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="savingCourse" @click="courseDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingCourse" @click="saveCourse">保存课程</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="chapterDialog"
      :title="editingChapterId ? '编辑章节' : '添加章节'"
      width="min(520px, 92vw)"
      :close-on-click-modal="!savingChapter"
      :close-on-press-escape="!savingChapter"
      :show-close="!savingChapter"
      @closed="resetChapterForm"
    >
      <el-form ref="chapterFormRef" :model="chapterForm" :rules="chapterRules" label-position="top">
        <el-form-item label="章节标题" prop="title">
          <el-input v-model.trim="chapterForm.title" placeholder="例如：第一章 课程导学" />
        </el-form-item>
        <el-form-item label="章节描述" prop="description">
          <el-input
            v-model.trim="chapterForm.description"
            maxlength="500"
            show-word-limit
            placeholder="简要说明本章学习内容"
          />
        </el-form-item>
        <el-form-item label="排序"><el-input-number v-model="chapterForm.sort_order" :min="0" :max="100000" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="savingChapter" @click="chapterDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingChapter" @click="saveChapter">保存章节</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="videoDialog"
      title="上传视频"
      width="min(520px, 92vw)"
      :close-on-click-modal="!uploading"
      :close-on-press-escape="!uploading"
      :show-close="!uploading"
    >
      <el-form ref="videoFormRef" :model="videoForm" :rules="videoRules" label-position="top">
        <el-form-item label="视频标题" prop="title">
          <el-input v-model.trim="videoForm.title" placeholder="请输入视频标题" />
        </el-form-item>
        <el-form-item label="视频描述" prop="description">
          <el-input
            v-model.trim="videoForm.description"
            maxlength="500"
            show-word-limit
            placeholder="简要介绍本节视频内容"
          />
        </el-form-item>
        <el-form-item label="排序"><el-input-number v-model="videoForm.sort_order" :min="0" :max="100000" /></el-form-item>
        <el-form-item label="视频文件" required>
          <label class="file-picker">
            <input
              :key="videoInputKey"
              type="file"
              accept=".mp4,.mov,.mkv,.avi,.webm,video/mp4,video/quicktime,video/x-matroska,video/webm"
              @change="selectVideoFile"
            />
            <span>选择视频文件</span>
            <strong>{{ videoFile?.name || '尚未选择文件' }}</strong>
          </label>
        </el-form-item>
      </el-form>
      <p class="dialog-tip">支持 MP4、MOV、MKV、AVI、WebM；大视频将在后台处理，完成后会提示结果。</p>
      <template #footer>
        <el-button :disabled="uploading" @click="videoDialog = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="uploadVideo">上传并处理</el-button>
      </template>
    </el-dialog>
  </section>
</template>
