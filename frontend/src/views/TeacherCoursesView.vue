<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import api from '../api/client'
import OverflowText from '../components/OverflowText.vue'
import { focusElement, useDialogFocus } from '../utils/dialogFocus'


const courses = ref([])
const categories = ref([])
const loading = ref(false)
const loadError = ref('')
const courseFormRef = ref(null)
const chapterFormRef = ref(null)
const videoFormRef = ref(null)
const videoTitleInput = ref(null)
const courseDialog = ref(false)
const chapterDialog = ref(false)
const videoDialog = ref(false)
const restoreCourseFocus = useDialogFocus(courseDialog)
const restoreChapterFocus = useDialogFocus(chapterDialog)
const chapterUploadButton = ref(null)
let videoEditorOpener = null
const videoDialogMode = ref('upload')
const selectedCourse = ref(null)
const selectedChapter = ref(null)
const selectedVideo = ref(null)
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
const uploadProgress = ref(0)
const cancellingUpload = ref(false)
let uploadController = null
let activeUploadToken = null
const savingCourse = ref(false)
const savingChapter = ref(false)
const processingVideoId = ref(null)
const chapterBusy = computed(() => savingChapter.value || uploading.value || processingVideoId.value !== null)
let disposed = false
let loadRequestSequence = 0
let videoMonitorSequence = 0
const activeVideoMonitors = new Map()
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
  const requestId = ++loadRequestSequence
  loading.value = true
  loadError.value = ''
  try {
    const [courseResponse, categoryResponse] = await Promise.all([
      api.get('/courses/mine'),
      api.get('/courses/categories'),
    ])
    if (disposed || requestId !== loadRequestSequence) return
    courses.value = courseResponse.data
    categories.value = categoryResponse.data
    // Refresh the chapter's video list without overwriting either unsaved form.
    if (chapterDialog.value && editingChapterId.value) {
      const currentCourse = courses.value.find((item) => item.id === selectedCourse.value?.id)
      const currentChapter = currentCourse?.chapters?.find((item) => item.id === editingChapterId.value)
      if (currentCourse && currentChapter) {
        selectedCourse.value = currentCourse
        selectedChapter.value = currentChapter
      }
    }
  } catch (error) {
    if (disposed || requestId !== loadRequestSequence) return
    loadError.value = error.message || '教学课程加载失败'
    ElMessage.error(error.message || '教学课程加载失败')
  } finally {
    if (!disposed && requestId === loadRequestSequence) loading.value = false
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
  if (chapterBusy.value) return
  selectedCourse.value = course
  selectedChapter.value = chapter
  videoDialog.value = false
  resetVideoForm()
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
  videoDialog.value = false
  resetVideoForm()
  selectedChapter.value = null
  selectedCourse.value = null
  videoEditorOpener = null
  editingChapterId.value = null
  Object.assign(chapterForm, { title: '', description: '', sort_order: 0 })
  chapterFormRef.value?.clearValidate()
}

async function saveChapter() {
  if (chapterBusy.value) return
  const valid = await chapterFormRef.value?.validate().catch(() => false)
  if (!valid || chapterBusy.value) return

  savingChapter.value = true
  try {
    if (editingChapterId.value) {
      await api.put(
        `/courses/${selectedCourse.value.id}/chapters/${editingChapterId.value}`,
        chapterForm,
      )
      if (disposed) return
      ElMessage.success('章节信息已更新')
    } else {
      const response = await api.post(`/courses/${selectedCourse.value.id}/chapters`, { ...chapterForm })
      if (disposed) return
      editingChapterId.value = response.data.id
      selectedChapter.value = { ...response.data, videos: response.data.videos || [] }
      ElMessage.success('章节创建成功')
    }
    await load()
  } catch (error) {
    if (!disposed) ElMessage.error(error.message || '章节保存失败')
  } finally {
    savingChapter.value = false
  }
}

function openVideo(course, chapter) {
  if (chapterBusy.value || videoDialog.value) return
  if (!chapterDialog.value) openChapter(course, chapter)
  videoEditorOpener = document.activeElement
  videoDialogMode.value = 'upload'
  selectedChapter.value = chapter
  selectedVideo.value = null
  videoFile.value = null
  Object.assign(videoForm, { title: '', description: '', sort_order: 0 })
  videoInputKey.value += 1
  videoFormRef.value?.clearValidate()
  videoDialog.value = true
  void focusVideoEditor()
}

function openVideoEdit(course, chapter, video) {
  if (chapterBusy.value || videoDialog.value) return
  videoEditorOpener = document.activeElement
  videoDialogMode.value = 'edit'
  selectedCourse.value = course
  selectedChapter.value = chapter
  selectedVideo.value = video
  videoFile.value = null
  Object.assign(videoForm, {
    title: video.title || '',
    description: video.description || '',
    sort_order: video.sort_order || 0,
  })
  videoInputKey.value += 1
  videoFormRef.value?.clearValidate()
  videoDialog.value = true
  void focusVideoEditor()
}

function openVideoReplace(course, chapter, video) {
  if (chapterBusy.value || videoDialog.value) return
  videoEditorOpener = document.activeElement
  videoDialogMode.value = 'replace'
  selectedCourse.value = course
  selectedChapter.value = chapter
  selectedVideo.value = video
  videoFile.value = null
  Object.assign(videoForm, {
    title: video.title || '',
    description: video.description || '',
    sort_order: video.sort_order || 0,
  })
  videoInputKey.value += 1
  videoFormRef.value?.clearValidate()
  videoDialog.value = true
  void focusVideoEditor()
}

async function focusVideoEditor() {
  await nextTick()
  if (disposed || !chapterDialog.value || !videoDialog.value) return
  videoTitleInput.value?.focus()
  videoTitleInput.value?.input?.scrollIntoView({ block: 'nearest', behavior: 'instant' })
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
  CANCELLED: '已终止',
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

function canChangeVideoContent(course, video) {
  return ['DRAFT', 'OFFLINE'].includes(course.status)
    && !['PENDING', 'PROCESSING'].includes(video.status)
}

function canDeleteVideo(course, video) {
  return ['DRAFT', 'OFFLINE'].includes(course.status)
    || ['UPLOADING', 'PENDING', 'PROCESSING', 'FAILED', 'CANCELLED'].includes(video.status)
}

function isVideoProcessing(video) {
  return ['UPLOADING', 'PENDING', 'PROCESSING'].includes(video.status)
}

function videoDialogTitle() {
  return { upload: '上传视频', edit: '编辑视频资料', replace: '替换视频文件' }[videoDialogMode.value]
}

function resetVideoForm() {
  if (uploading.value) return
  videoDialogMode.value = 'upload'
  selectedVideo.value = null
  videoFile.value = null
  Object.assign(videoForm, { title: '', description: '', sort_order: 0 })
  videoInputKey.value += 1
  videoFormRef.value?.clearValidate()
}

async function closeVideoEditor() {
  if (uploading.value) return
  videoDialog.value = false
  resetVideoForm()
  await nextTick()
  if (!disposed && chapterDialog.value) {
    if (videoEditorOpener?.closest('.chapter-editor-dialog') && focusElement(videoEditorOpener)) return
    focusElement(chapterUploadButton.value?.$el)
  }
}

function selectVideoFile(event) {
  videoFile.value = event.target.files?.[0] || null
}

async function cancelVideoUpload() {
  if (!uploading.value || !activeUploadToken || cancellingUpload.value) return
  cancellingUpload.value = true
  const token = activeUploadToken
  uploadController?.abort()
  try {
    const response = await api.post(`/videos/uploads/${token}/cancel`)
    ElMessage.success(response.message || '视频上传已取消')
  } catch (error) {
    ElMessage.error(error.message || '取消上传失败，请稍后检查视频列表')
  } finally {
    videoFile.value = null
    videoInputKey.value += 1
    uploadProgress.value = 0
    uploading.value = false
    cancellingUpload.value = false
    uploadController = null
    activeUploadToken = null
  }
}

async function saveVideo() {
  if (chapterBusy.value) return
  const valid = await videoFormRef.value?.validate().catch(() => false)
  if (!valid || chapterBusy.value) return

  if (videoDialogMode.value !== 'edit' && !videoFile.value) {
    ElMessage.warning('请选择视频文件')
    return
  }
  uploading.value = true
  if (videoDialogMode.value === 'replace') {
    try {
      await ElMessageBox.confirm(
        '替换会创建新的视频记录，并清除原视频对应的学习进度、笔记和答疑，确认继续？',
        '确认替换视频',
        { confirmButtonText: '确认替换', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      uploading.value = false
      return
    }
  }
  if (disposed) { uploading.value = false; return }

  if (videoDialogMode.value === 'edit') {
    let succeeded = false
    try {
      await api.put(`/videos/${selectedVideo.value.id}`, {
        title: videoForm.title,
        description: videoForm.description,
        sort_order: videoForm.sort_order,
      })
      if (disposed) return
      ElMessage.success('视频资料已更新')
      await load()
      succeeded = true
    } catch (error) {
      if (!disposed) ElMessage.error(error.message || '视频资料保存失败')
    } finally {
      uploading.value = false
    }
    if (succeeded && !disposed) await closeVideoEditor()
    return
  }

  const data = new FormData()
  if (videoDialogMode.value === 'upload') data.append('chapter_id', selectedChapter.value.id)
  data.append('title', videoForm.title)
  data.append('description', videoForm.description)
  data.append('sort_order', videoForm.sort_order)
  data.append('video_file', videoFile.value)
  const cancellableUpload = videoDialogMode.value === 'upload'
  if (cancellableUpload) {
    activeUploadToken = window.crypto.randomUUID()
    uploadController = new AbortController()
    data.append('upload_token', activeUploadToken)
    uploadProgress.value = 0
  }
  uploading.value = true
  try {
    const endpoint = videoDialogMode.value === 'replace'
      ? `/videos/${selectedVideo.value.id}/replace`
      : '/videos/upload'
    const response = await api.post(endpoint, data, {
      timeout: 0,
      signal: uploadController?.signal,
      onUploadProgress: cancellableUpload
        ? (event) => {
            if (event.total) uploadProgress.value = Math.min(99, Math.round((event.loaded / event.total) * 100))
          }
        : undefined,
    })
    if (disposed) return
    if (response.data.status === 'READY') {
      ElMessage.success(videoDialogMode.value === 'replace' ? '视频替换完成' : '视频处理完成')
      await load()
    } else if (response.data.status === 'FAILED') {
      ElMessage.error(response.data.error_message || '视频处理失败')
      await load()
    } else {
      ElMessage.success(videoDialogMode.value === 'replace' ? '替换视频已提交后台处理' : '视频已提交后台处理，可继续编辑其他内容')
      await load()
      void monitorVideo(response.data.id)
    }
    if (disposed) return
    uploading.value = false
    await closeVideoEditor()
  } catch (error) {
    if (!disposed && !error?.canceled && !cancellingUpload.value) {
      ElMessage.error(error.message || (videoDialogMode.value === 'replace' ? '视频替换失败' : '视频上传失败'))
    }
  } finally {
    uploading.value = false
    if (!cancellingUpload.value) {
      uploadProgress.value = 0
      uploadController = null
      activeUploadToken = null
    }
  }
}

async function monitorVideo(videoId) {
  const monitorId = ++videoMonitorSequence
  activeVideoMonitors.set(videoId, monitorId)
  let consecutiveErrors = 0
  for (let attempt = 0; attempt < 150 && !disposed && activeVideoMonitors.get(videoId) === monitorId; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2000))
    if (disposed || activeVideoMonitors.get(videoId) !== monitorId) return
    try {
      const response = await api.get(`/videos/${videoId}/status`)
      consecutiveErrors = 0
      if (response.data.status === 'READY') {
        ElMessage.success(`视频“${response.data.title}”处理完成`)
        await load()
        activeVideoMonitors.delete(videoId)
        return
      }
      if (response.data.status === 'FAILED') {
        ElMessage.error(response.data.error_message || '后台视频处理失败')
        await load()
        activeVideoMonitors.delete(videoId)
        return
      }
      if (response.data.status === 'CANCELLED') {
        await load()
        activeVideoMonitors.delete(videoId)
        return
      }
    } catch (error) {
      if (Number(error?.code) === 404) {
        activeVideoMonitors.delete(videoId)
        await load()
        return
      }
      consecutiveErrors += 1
      if (consecutiveErrors >= 3) {
        ElMessage.warning('暂时无法获取视频处理状态，请稍后刷新课程列表')
        activeVideoMonitors.delete(videoId)
        return
      }
    }
  }
  if (!disposed && activeVideoMonitors.get(videoId) === monitorId) {
    activeVideoMonitors.delete(videoId)
    ElMessage.warning('视频仍在后台处理，请稍后刷新课程列表')
  }
}

async function retryVideo(video) {
  if (chapterBusy.value) return
  processingVideoId.value = video.id
  try {
    const response = await api.post(`/videos/${video.id}/retry`, null, { timeout: 0 })
    if (response.data.status === 'READY') {
      ElMessage.success('视频重新转码完成')
      await load()
    } else if (response.data.status === 'FAILED') {
      ElMessage.error(response.data.error_message || '视频重新转码失败')
      await load()
    } else {
      ElMessage.success('视频已重新提交后台处理')
      await load()
      void monitorVideo(response.data.id)
    }
  } catch (error) {
    ElMessage.error(error.message || '视频重新处理失败')
  } finally {
    processingVideoId.value = null
  }
}

async function removeVideo(course, video) {
  if (chapterBusy.value) return
  processingVideoId.value = video.id
  try {
    const processing = isVideoProcessing(video)
    await ElMessageBox.confirm(
      processing
        ? `“${video.title}”仍在转码。继续将终止任务并删除视频，确定吗？`
        : `删除“${video.title}”会同时清除相关学习进度、笔记和答疑，确定继续吗？`,
      processing ? '终止并删除视频' : '删除视频',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    processingVideoId.value = null
    return
  }
  processingVideoId.value = video.id
  try {
    await api.delete(`/videos/${video.id}`)
    activeVideoMonitors.delete(video.id)
    ElMessage.success(isVideoProcessing(video) ? '转码任务已终止，视频已删除' : '视频已删除')
    await load()
  } catch (error) {
    ElMessage.error(error.message || '视频删除失败')
  } finally {
    processingVideoId.value = null
  }
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
    for (const chapter of course.chapters || []) {
      for (const video of chapter.videos || []) activeVideoMonitors.delete(video.id)
    }
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
    for (const video of chapter.videos || []) activeVideoMonitors.delete(video.id)
    ElMessage.success('章节已删除')
    await load()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '章节删除失败')
  }
}

onMounted(load)
onBeforeUnmount(() => {
  disposed = true
  if (uploading.value && activeUploadToken) {
    const token = activeUploadToken
    uploadController?.abort()
    void api.post(`/videos/uploads/${token}/cancel`).catch(() => {})
  }
  activeVideoMonitors.clear()
  releaseCourseCoverPreview()
})
</script>

<template>
  <section class="page-section teacher-page">
    <div class="page-heading">
      <div>
        <p class="eyebrow">教师工作台</p>
        <h1>教学管理</h1>
        <p>创建课程、组织章节并上传视频；发布中也可编辑资料，删除章节等操作需先下线。</p>
      </div>
      <el-button type="primary" size="large" @click="openCourse()">＋ 创建课程</el-button>
    </div>

    <el-result v-if="loadError" icon="error" title="教学课程加载失败" :sub-title="loadError">
      <template #extra><el-button @click="load">重新加载</el-button></template>
    </el-result>
    <div v-else class="management-surface">
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
                    <div v-for="video in chapter.videos" :key="video.id" class="video-management-row">
                      <div class="video-status">
                        <span :class="`video-state state-${video.status.toLowerCase()}`"></span>
                        <span>{{ video.title }} · {{ statusLabel(video.status) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="chapter-actions">
                  <el-button
                    v-if="canMaintain(scope.row)"
                    :disabled="chapterBusy"
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
                  <el-button :disabled="!canMaintain(scope.row) || chapterBusy" @click="openVideo(scope.row, chapter)">上传视频</el-button>
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
              <OverflowText class="course-name-cell" :text="scope.row.name" label="查看课程名称全文" />
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
      @close-auto-focus="restoreCourseFocus"
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
      @close-auto-focus="restoreChapterFocus"
      :title="editingChapterId ? '编辑章节' : '添加章节'"
      width="min(960px, 94vw)"
      class="chapter-editor-dialog"
      :close-on-click-modal="!chapterBusy"
      :close-on-press-escape="!chapterBusy"
      :show-close="!chapterBusy"
      @closed="resetChapterForm"
    >
      <p class="dialog-tip chapter-context">所属课程：{{ selectedCourse?.name }}。章节资料和视频分别保存，成功后立即生效。</p>
      <el-form ref="chapterFormRef" :model="chapterForm" :rules="chapterRules" :disabled="chapterBusy" label-position="top">
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
      <section class="chapter-video-section" aria-label="本章节视频管理">
        <div class="chapter-video-heading">
          <div><h3>本章节视频</h3><span>{{ selectedChapter?.videos?.length || 0 }} 个视频 · 上传到当前章节</span></div>
          <el-button ref="chapterUploadButton" :disabled="!editingChapterId || chapterBusy || videoDialog" @click="openVideo(selectedCourse, selectedChapter)">上传视频</el-button>
        </div>
        <p v-if="!editingChapterId" class="dialog-tip">请先保存章节资料，再上传本章节的视频。</p>
        <div v-else class="chapter-editor-videos">
          <article v-for="video in selectedChapter?.videos || []" :key="video.id" class="chapter-editor-video">
            <div class="chapter-editor-video-copy"><OverflowText :text="video.title" label="查看视频标题全文" /><small>{{ statusLabel(video.status) }} · 排序 {{ video.sort_order || 0 }}</small></div>
            <div class="chapter-editor-video-actions">
              <el-button :disabled="chapterBusy || videoDialog" @click="openVideoEdit(selectedCourse, selectedChapter, video)">编辑视频</el-button>
              <el-button v-if="['FAILED', 'CANCELLED'].includes(video.status)" :disabled="chapterBusy || videoDialog" @click="retryVideo(video)">重新处理</el-button>
              <el-button v-if="canChangeVideoContent(selectedCourse, video)" :disabled="chapterBusy || videoDialog" @click="openVideoReplace(selectedCourse, selectedChapter, video)">替换文件</el-button>
              <el-button v-if="canDeleteVideo(selectedCourse, video)" :disabled="chapterBusy || videoDialog" @click="removeVideo(selectedCourse, video)">{{ isVideoProcessing(video) ? '终止并删除' : '删除视频' }}</el-button>
            </div>
          </article>
          <el-empty v-if="!selectedChapter?.videos?.length" description="本章节还没有视频" :image-size="48" />
        </div>
        <section v-if="videoDialog" class="chapter-video-form" :aria-label="videoDialogTitle()">
        <h3>{{ videoDialogTitle() }}</h3>
        <el-form ref="videoFormRef" :model="videoForm" :rules="videoRules" :disabled="chapterBusy" label-position="top">
        <el-form-item label="视频标题" prop="title">
          <el-input ref="videoTitleInput" v-model.trim="videoForm.title" placeholder="请输入视频标题" />
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
        <el-form-item v-if="videoDialogMode !== 'edit'" label="视频文件" required>
          <label class="file-picker">
            <input
              :key="videoInputKey"
              type="file"
              :disabled="chapterBusy"
              accept=".mp4,.mov,.mkv,.avi,.webm,video/mp4,video/quicktime,video/x-matroska,video/webm"
              @change="selectVideoFile"
            />
            <span>{{ videoDialogMode === 'replace' ? '选择新文件' : '选择视频文件' }}</span>
            <strong>{{ videoFile?.name || '尚未选择文件' }}</strong>
          </label>
        </el-form-item>
      </el-form>
      <p v-if="videoDialogMode === 'upload'" class="dialog-tip">
        支持 MP4、MOV、MKV、AVI、WebM；大视频将在后台处理，完成后会提示结果。
      </p>
      <el-progress v-if="uploading && videoDialogMode === 'upload'" :percentage="uploadProgress" :stroke-width="8" />
      <p v-else-if="videoDialogMode === 'replace'" class="dialog-tip video-destructive-tip">
        替换仅允许草稿或已下线课程。系统会创建新视频并清除原视频对应的学习进度、笔记和答疑。
      </p>
      <p v-else class="dialog-tip">修改标题、描述和排序不会影响学生已有学习记录。</p>
      <div class="chapter-video-form-actions">
        <el-button :disabled="chapterBusy" @click="closeVideoEditor">取消视频编辑</el-button>
        <el-button
          v-if="uploading && videoDialogMode === 'upload'"
          :loading="cancellingUpload"
          @click="cancelVideoUpload"
        >取消上传</el-button>
        <el-button type="primary" :loading="uploading" @click="saveVideo">
          {{ videoDialogMode === 'edit' ? '保存修改' : (videoDialogMode === 'replace' ? '替换并处理' : '上传并处理') }}
        </el-button>
      </div>
      </section>
      </section>
      <template #footer>
        <el-button :disabled="chapterBusy" @click="chapterDialog = false">关闭</el-button>
        <el-button type="primary" :disabled="uploading || processingVideoId !== null" :loading="savingChapter" @click="saveChapter">保存章节</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.chapter-context { white-space: pre-wrap; overflow-wrap: anywhere; }
.chapter-video-section { margin-top: 20px; border-top: 1px solid var(--line); padding-top: 18px; }
.chapter-video-heading, .chapter-editor-video { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.chapter-video-heading h3, .chapter-video-form h3 { margin: 0 0 8px; font-size: 16px; }
.chapter-video-heading span, .chapter-editor-video-copy small { color: var(--ink-600); font-size: 12px; }
.chapter-editor-videos { max-height: 260px; overflow: auto; overscroll-behavior: contain; margin-top: 12px; border: 1px solid var(--line); border-radius: 6px; }
.chapter-editor-video { padding: 12px; border-bottom: 1px solid var(--line); }
.chapter-editor-video:last-child { border-bottom: 0; }
.chapter-editor-video-copy { flex: 1; min-width: 0; }
.chapter-editor-video-actions { display: flex; flex-wrap: wrap; gap: 6px; flex-shrink: 0; }
.chapter-editor-video-actions :deep(.el-button) { margin: 0; }
.chapter-video-form { margin-top: 16px; padding: 16px; border: 1px solid var(--line); border-radius: 6px; background: #f8f9fa; }
.chapter-video-form-actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 8px; }
@media (max-width: 620px) {
  .chapter-editor-video { align-items: stretch; flex-direction: column; gap: 10px; }
  .chapter-editor-video-actions { flex-shrink: 1; }
  .chapter-video-form { padding: 12px; }
}
</style>
