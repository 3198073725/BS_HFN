<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import api from '../api/client'
import VideoPlayer from '../components/VideoPlayer.vue'
import { useAuthStore } from '../stores/auth'


const route = useRoute()
const auth = useAuthStore()
const course = ref(null)
const loading = ref(false)
const errorMessage = ref('')
const selectedVideo = ref(null)
const videoPlayer = ref(null)
const learningLoading = ref(false)
const actionLoading = ref('')
const studyTab = ref('notes')
const progress = ref(null)
const queuedProgressCount = ref(0)
const startTime = ref(0)
const currentTime = ref(0)
const notes = ref([])
const questions = ref([])
const savingProgress = ref(false)
const noteForm = reactive({ content: '' })
const questionForm = reactive({ title: '', content: '' })
const learningState = reactive({ joined: false, favorited: false })
const classDialogVisible = ref(false)
const classOptions = ref([])
const classOptionsLoading = ref(false)
const joiningClassId = ref(null)
const isStudent = computed(() => auth.user?.role === 'STUDENT')
let lastPosition = null
let pendingWatchDuration = 0
let lastSaveAt = Date.now()
let courseRequestSequence = 0
let courseStateRequestSequence = 0
let learningRequestSequence = 0

async function loadCourse() {
  const requestId = ++courseRequestSequence
  const courseId = String(route.params.id)
  loading.value = true
  errorMessage.value = ''
  course.value = null
  selectedVideo.value = null
  Object.assign(learningState, { joined: false, favorited: false })
  classOptions.value = []
  classDialogVisible.value = false
  resetLearningContext()
  try {
    const response = await api.get(`/courses/${courseId}`, { authMode: 'optional' })
    if (requestId !== courseRequestSequence || String(route.params.id) !== courseId) return
    course.value = response.data
    selectedVideo.value =
      course.value.chapters
        .flatMap((chapter) => chapter.videos)
        .find((video) => video.status === 'READY') || null
    if (isStudent.value) await loadCourseState(courseId)
  } catch (error) {
    if (requestId !== courseRequestSequence || String(route.params.id) !== courseId) return
    errorMessage.value = error.message || '课程加载失败'
    ElMessage.error(errorMessage.value)
  } finally {
    if (requestId === courseRequestSequence) loading.value = false
  }
}

async function loadCourseState(courseId = String(route.params.id)) {
  const requestId = ++courseStateRequestSequence
  try {
    const response = await api.get(`/learning/courses/${courseId}/state`)
    if (requestId !== courseStateRequestSequence || String(route.params.id) !== courseId) return
    Object.assign(learningState, response.data)
    if (learningState.joined && selectedVideo.value) await loadLearningContext()
  } catch (error) {
    if (requestId === courseStateRequestSequence && String(route.params.id) === courseId) {
      ElMessage.error(error.message || '学习状态加载失败')
    }
  }
}

async function joinCourse() {
  if (actionLoading.value) return
  actionLoading.value = 'join'
  try {
    await api.post(`/learning/courses/${route.params.id}/join`)
    learningState.joined = true
    ElMessage.success('课程加入成功，学习进度将自动保存')
    if (selectedVideo.value) await loadLearningContext()
  } catch (error) {
    ElMessage.error(error.message || '加入课程失败')
  } finally {
    actionLoading.value = ''
  }
}

async function openClassDialog() {
  if (classOptionsLoading.value) return
  classOptionsLoading.value = true
  try {
    const response = await api.get(`/courses/${route.params.id}/classes`)
    classOptions.value = response.data
    if (!classOptions.value.length) {
      ElMessage.info('授课教师暂未给这门课程关联班级')
      return
    }
    classDialogVisible.value = true
  } catch (error) {
    ElMessage.error(error.message || '班级列表加载失败')
  } finally {
    classOptionsLoading.value = false
  }
}

async function applyForClass(classroom) {
  if (joiningClassId.value !== null || classroom.joined || classroom.request_status === 'PENDING') return
  joiningClassId.value = classroom.id
  try {
    await api.post(`/courses/${route.params.id}/classes/${classroom.id}/apply`)
    classroom.request_status = 'PENDING'
    ElMessage.success(`已申请加入“${classroom.name}”，请等待教师审批`)
  } catch (error) {
    ElMessage.error(error.message || '入班申请提交失败')
  } finally {
    joiningClassId.value = null
  }
}

async function toggleFavorite() {
  if (actionLoading.value) return
  actionLoading.value = 'favorite'
  try {
    if (learningState.favorited) {
      await api.delete(`/learning/courses/${route.params.id}/favorite`)
      learningState.favorited = false
      ElMessage.success('已取消收藏')
    } else {
      await api.post(`/learning/courses/${route.params.id}/favorite`)
      learningState.favorited = true
      ElMessage.success('课程已收藏')
    }
  } catch (error) {
    ElMessage.error(error.message || '收藏状态更新失败')
  } finally {
    actionLoading.value = ''
  }
}

async function selectVideo(video) {
  if (selectedVideo.value?.id === video.id) return
  await saveProgress(true)
  selectedVideo.value = video
  resetLearningContext()
  if (isStudent.value && learningState.joined) await loadLearningContext()
}

async function loadLearningContext() {
  if (!selectedVideo.value) return
  const requestId = ++learningRequestSequence
  const videoId = selectedVideo.value.id
  learningLoading.value = true
  resetLearningContext(false)
  try {
    const [progressResponse, notesResponse, questionsResponse] = await Promise.all([
      api.get(`/learning/videos/${videoId}/progress`),
      api.get(`/learning/videos/${videoId}/notes`),
      api.get('/questions', { params: { video_id: videoId } }),
    ])
    if (requestId !== learningRequestSequence || selectedVideo.value?.id !== videoId) return
    progress.value = progressResponse.data
    startTime.value = progressResponse.data.current_time || 0
    currentTime.value = startTime.value
    notes.value = notesResponse.data
    questions.value = questionsResponse.data
  } catch (error) {
    if (requestId === learningRequestSequence && selectedVideo.value?.id === videoId) {
      ElMessage.error(error.message || '学习数据加载失败')
    }
  } finally {
    if (requestId === learningRequestSequence) learningLoading.value = false
  }
}

function resetLearningContext(invalidateRequest = true) {
  if (invalidateRequest) {
    learningRequestSequence += 1
    learningLoading.value = false
  }
  progress.value = null
  startTime.value = 0
  currentTime.value = 0
  notes.value = []
  questions.value = []
  lastPosition = null
  pendingWatchDuration = 0
  lastSaveAt = Date.now()
}

function handleTimeUpdate(value) {
  const time = Number(value || 0)
  if (lastPosition !== null) {
    const delta = time - lastPosition
    if (delta > 0 && delta <= 3) pendingWatchDuration += delta
  }
  lastPosition = time
  currentTime.value = time
  if (Date.now() - lastSaveAt >= 10000 && pendingWatchDuration >= 1) void saveProgress()
}

function handleCheckpoint(value) {
  currentTime.value = Number(value || 0)
  void saveProgress(true)
}

async function saveProgress(force = false) {
  if (!isStudent.value || !learningState.joined || !selectedVideo.value || savingProgress.value) return
  const watchDelta = Math.min(60, Math.floor(pendingWatchDuration))
  if (!force && watchDelta < 1) return
  if (force && watchDelta < 1 && Math.abs(currentTime.value - startTime.value) < 0.5) return

  const savedVideoId = selectedVideo.value.id
  savingProgress.value = true
  lastSaveAt = Date.now()
  try {
    const response = await api.put(`/learning/videos/${savedVideoId}/progress`, {
      current_time: currentTime.value,
      watch_duration_delta: watchDelta,
    })
    if (selectedVideo.value?.id === savedVideoId) progress.value = response.data
    pendingWatchDuration = Math.max(0, pendingWatchDuration - watchDelta)
  } catch (error) {
    if (isConnectionError(error)) {
      queueProgress({
        video_id: savedVideoId,
        current_time: currentTime.value,
        watch_duration_delta: watchDelta,
      })
      pendingWatchDuration = Math.max(0, pendingWatchDuration - watchDelta)
      if (force) ElMessage.warning('网络不可用，学习进度已保存在本机，恢复连接后会自动补传')
    } else if (force) {
      ElMessage.error(error.message || '学习进度保存失败')
    }
  } finally {
    savingProgress.value = false
  }
}

function progressQueueKey() {
  return `bs-hfn:progress-queue:${auth.user?.id || 'anonymous'}`
}

function readProgressQueue() {
  try {
    const value = JSON.parse(localStorage.getItem(progressQueueKey()) || '[]')
    return Array.isArray(value) ? value : []
  } catch {
    return []
  }
}

function writeProgressQueue(items) {
  const limited = items.slice(-200)
  localStorage.setItem(progressQueueKey(), JSON.stringify(limited))
  queuedProgressCount.value = limited.length
}

function queueProgress(payload) {
  writeProgressQueue([...readProgressQueue(), { ...payload, queued_at: Date.now() }])
}

async function flushProgressQueue() {
  if (!isStudent.value || !navigator.onLine) return
  const queued = readProgressQueue()
  if (!queued.length) {
    queuedProgressCount.value = 0
    return
  }
  const remaining = [...queued]
  let sent = 0
  while (remaining.length) {
    const item = remaining[0]
    try {
      await api.put(`/learning/videos/${item.video_id}/progress`, {
        current_time: item.current_time,
        watch_duration_delta: item.watch_duration_delta,
      })
      remaining.shift()
      sent += 1
    } catch (error) {
      if (!isConnectionError(error)) remaining.shift()
      break
    }
  }
  writeProgressQueue(remaining)
  if (sent) ElMessage.success(`已补传 ${sent} 条离线学习进度`)
}

function isConnectionError(error) {
  const message = String(error?.message || '')
  return !navigator.onLine || message.includes('网络连接失败') || message.includes('请求超时')
}

async function createNote() {
  const content = noteForm.content.trim()
  if (!content) {
    ElMessage.warning('请输入笔记内容')
    return
  }
  actionLoading.value = 'note'
  try {
    const response = await api.post(`/learning/videos/${selectedVideo.value.id}/notes`, {
      video_time: currentTime.value,
      content,
    })
    notes.value.push(response.data)
    notes.value.sort((left, right) => left.video_time - right.video_time)
    noteForm.content = ''
    ElMessage.success('笔记已记录')
  } catch (error) {
    ElMessage.error(error.message || '笔记保存失败')
  } finally {
    actionLoading.value = ''
  }
}

async function removeNote(note) {
  try {
    await ElMessageBox.confirm('确认删除这条视频笔记？', '删除笔记', { type: 'warning' })
    await api.delete(`/learning/notes/${note.id}`)
    notes.value = notes.value.filter((item) => item.id !== note.id)
    ElMessage.success('笔记已删除')
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(error.message || '笔记删除失败')
  }
}

async function createQuestion() {
  const title = questionForm.title.trim()
  const content = questionForm.content.trim()
  if (!title || !content) {
    ElMessage.warning('请填写问题标题和详细内容')
    return
  }
  actionLoading.value = 'question'
  try {
    const response = await api.post('/questions', {
      video_id: selectedVideo.value.id,
      video_time: currentTime.value,
      title,
      content,
    })
    questions.value.unshift(response.data)
    Object.assign(questionForm, { title: '', content: '' })
    ElMessage.success('问题已提交给授课教师')
  } catch (error) {
    ElMessage.error(error.message || '问题提交失败')
  } finally {
    actionLoading.value = ''
  }
}

async function closeQuestion(question) {
  try {
    const response = await api.post(`/questions/${question.id}/close`)
    const index = questions.value.findIndex((item) => item.id === question.id)
    if (index >= 0) questions.value[index] = response.data
    ElMessage.success('问题已关闭')
  } catch (error) {
    ElMessage.error(error.message || '问题关闭失败')
  }
}

function readyVideos(chapter) {
  return chapter.videos.filter((video) => video.status === 'READY')
}

function formatTime(seconds) {
  const value = Math.max(0, Math.floor(Number(seconds || 0)))
  const minutes = Math.floor(value / 60)
  return `${String(minutes).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`
}

function questionStatus(status) {
  return { WAITING: '等待回答', ANSWERED: '已回答', CLOSED: '已关闭' }[status] || status
}

function seekTo(seconds) {
  videoPlayer.value?.seekTo(Number(seconds || 0))
  currentTime.value = Number(seconds || 0)
}

watch(() => route.params.id, async (nextId, previousId) => {
  if (nextId === previousId) return
  await saveProgress(true)
  void loadCourse()
})
onMounted(() => {
  queuedProgressCount.value = readProgressQueue().length
  window.addEventListener('online', flushProgressQueue)
  void loadCourse().then(flushProgressQueue)
})
onBeforeUnmount(() => {
  courseRequestSequence += 1
  courseStateRequestSequence += 1
  learningRequestSequence += 1
  void saveProgress(true)
  window.removeEventListener('online', flushProgressQueue)
})
</script>

<template>
  <section class="page-section course-detail-page" v-loading="loading">
    <template v-if="course">
      <RouterLink class="breadcrumb-link" to="/courses">← 返回课程中心</RouterLink>

      <header
        class="course-detail-hero"
        :class="{ 'has-cover': course.cover_url }"
        :style="course.cover_url ? { backgroundImage: `url(&quot;${course.cover_url}&quot;)` } : null"
      >
        <div>
          <div class="course-detail-meta">
            <span>{{ course.category_name || '通识课程' }}</span>
            <i></i>
            <span>已发布</span>
          </div>
          <h1>{{ course.name }}</h1>
          <p>{{ course.description || '教师暂未填写课程简介。' }}</p>
          <div class="course-hero-footer">
            <RouterLink class="teacher-line teacher-profile-link" :to="`/users/${course.teacher_id}`">
              <span class="teacher-avatar">
                <img v-if="course.teacher_avatar_url" :src="course.teacher_avatar_url" alt="" />
                <template v-else>{{ course.teacher_name?.slice(0, 1) || '师' }}</template>
              </span>
              <span><small>授课教师</small><strong>{{ course.teacher_name || '待更新' }}</strong></span>
            </RouterLink>
            <div class="course-learning-actions">
              <template v-if="isStudent">
                <button
                  class="hero-small-button primary"
                  type="button"
                  :disabled="learningState.joined || actionLoading === 'join'"
                  @click="joinCourse"
                >
                  {{ learningState.joined ? '✓ 已加入课程' : '＋ 加入课程' }}
                </button>
                <button
                  class="hero-small-button"
                  type="button"
                  :disabled="actionLoading === 'favorite'"
                  @click="toggleFavorite"
                >
                  {{ learningState.favorited ? '★ 已收藏' : '☆ 收藏课程' }}
                </button>
                <button
                  class="hero-small-button"
                  type="button"
                  :disabled="classOptionsLoading"
                  @click="openClassDialog"
                >
                  {{ classOptionsLoading ? '读取班级中' : '加入班级' }}
                </button>
              </template>
              <RouterLink
                v-else-if="!auth.isAuthenticated"
                class="hero-small-button primary"
                :to="{ name: 'login', query: { redirect: route.fullPath } }"
              >
                登录后加入
              </RouterLink>
            </div>
          </div>
        </div>
        <div v-if="!course.cover_url" class="course-detail-mark" aria-hidden="true">{{ course.name?.slice(0, 1) || '课' }}</div>
      </header>

      <div class="learning-layout">
        <section class="player-panel">
          <div class="panel-heading">
            <div>
              <p class="eyebrow">当前播放</p>
              <h2>{{ selectedVideo?.title || '选择一个视频开始学习' }}</h2>
            </div>
            <div class="player-status-group">
              <span v-if="progress" class="progress-chip">
                {{ progress.status === 'COMPLETED' ? '已完成' : `${progress.progress}%` }}
              </span>
              <span v-if="queuedProgressCount" class="offline-progress-chip">{{ queuedProgressCount }} 条进度待补传</span>
              <span v-if="selectedVideo" class="playing-status"><i></i> 可播放</span>
            </div>
          </div>
          <VideoPlayer
            v-if="selectedVideo && !learningLoading"
            ref="videoPlayer"
            :key="selectedVideo.id"
            :source="selectedVideo.hls_url"
            :start-time="startTime"
            @timeupdate="handleTimeUpdate"
            @checkpoint="handleCheckpoint"
          />
          <div v-else-if="learningLoading" class="player-placeholder compact-player">
            <strong>正在恢复学习进度…</strong>
          </div>
          <div v-else class="player-placeholder">
            <span>▶</span>
            <strong>暂无可播放视频</strong>
            <p>课程视频准备好后会显示在这里。</p>
          </div>
          <p v-if="isStudent && !learningState.joined && selectedVideo" class="join-reminder">
            加入课程后可自动保存进度、记录笔记并向教师提问。
          </p>
        </section>

        <aside class="chapter-panel">
          <div class="panel-heading compact">
            <div>
              <p class="eyebrow">课程内容</p>
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
                  @click="selectVideo(video)"
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

      <section v-if="isStudent && learningState.joined && selectedVideo" class="study-workspace">
        <div class="study-tabs" role="tablist" aria-label="学习工具">
          <button :class="{ active: studyTab === 'notes' }" type="button" @click="studyTab = 'notes'">
            视频笔记 <span>{{ notes.length }}</span>
          </button>
          <button :class="{ active: studyTab === 'questions' }" type="button" @click="studyTab = 'questions'">
            我的提问 <span>{{ questions.length }}</span>
          </button>
          <p v-if="progress">已学到 {{ formatTime(progress.current_time) }} · {{ progress.progress }}%</p>
        </div>

        <div v-if="studyTab === 'notes'" class="study-tab-content">
          <div class="study-composer">
            <div>
              <p class="eyebrow">学习笔记</p>
              <h3>记录当前时间点</h3>
              <small>笔记将定位到 {{ formatTime(currentTime) }}</small>
            </div>
            <el-input
              v-model="noteForm.content"
              type="textarea"
              :rows="3"
              maxlength="2000"
              show-word-limit
              placeholder="写下此处的重点、公式或思考…"
            />
            <el-button type="primary" :loading="actionLoading === 'note'" @click="createNote">
              保存笔记
            </el-button>
          </div>
          <div class="study-list">
            <article v-for="note in notes" :key="note.id" class="study-item note-item">
              <button class="time-anchor" type="button" @click="seekTo(note.video_time)">
                {{ formatTime(note.video_time) }}
              </button>
              <p>{{ note.content }}</p>
              <button class="text-danger" type="button" @click="removeNote(note)">删除</button>
            </article>
            <el-empty v-if="!notes.length" description="还没有笔记，播放视频时记录第一条吧" :image-size="68" />
          </div>
        </div>

        <div v-else class="study-tab-content">
          <div class="study-composer question-composer">
            <div>
              <p class="eyebrow">课程提问</p>
              <h3>在 {{ formatTime(currentTime) }} 向教师提问</h3>
            </div>
            <el-input v-model="questionForm.title" maxlength="200" placeholder="用一句话概括问题" />
            <el-input
              v-model="questionForm.content"
              type="textarea"
              :rows="3"
              maxlength="5000"
              show-word-limit
              placeholder="说明你不理解的地方，便于教师准确回答…"
            />
            <el-button type="primary" :loading="actionLoading === 'question'" @click="createQuestion">
              提交问题
            </el-button>
          </div>
          <div class="study-list question-list">
            <article v-for="question in questions" :key="question.id" class="study-item question-item">
              <div class="question-heading">
                <button class="time-anchor" type="button" @click="seekTo(question.video_time)">
                  {{ formatTime(question.video_time) }}
                </button>
                <strong>{{ question.title }}</strong>
                <span :class="`question-status status-${question.status.toLowerCase()}`">
                  {{ questionStatus(question.status) }}
                </span>
              </div>
              <p>{{ question.content }}</p>
              <div v-if="question.answer" class="answer-box">
                <strong>{{ question.answer.teacher_name || '授课教师' }}的回答</strong>
                <p>{{ question.answer.content }}</p>
              </div>
              <button
                v-if="question.status !== 'CLOSED'"
                class="close-question"
                type="button"
                @click="closeQuestion(question)"
              >
                关闭问题
              </button>
            </article>
            <el-empty v-if="!questions.length" description="当前视频还没有提问" :image-size="68" />
          </div>
        </div>
      </section>
    </template>

    <el-dialog
      v-model="classDialogVisible"
      title="选择课程班级"
      width="min(560px, calc(100vw - 28px))"
      class="course-class-dialog"
    >
      <p class="course-class-dialog-tip">提交申请后，班级教师同意才会正式加入并同步班级课程。</p>
      <div class="course-class-options">
        <article v-for="classroom in classOptions" :key="classroom.id" class="course-class-option">
          <span class="course-class-mark">班</span>
          <div>
            <strong>{{ classroom.name }}</strong>
            <p>{{ classroom.description || '授课教师暂未填写班级说明。' }}</p>
            <small>{{ classroom.teacher_name }} · {{ classroom.member_count }} 名学生</small>
          </div>
          <el-button
            :type="classroom.joined || classroom.request_status === 'PENDING' ? '' : 'primary'"
            :disabled="classroom.joined || classroom.request_status === 'PENDING' || joiningClassId !== null"
            :loading="joiningClassId === classroom.id"
            @click="applyForClass(classroom)"
          >
            {{ classroom.joined ? '已加入' : classroom.request_status === 'PENDING' ? '待教师审批' : classroom.request_status === 'REJECTED' ? '再次申请' : '申请加入' }}
          </el-button>
        </article>
      </div>
    </el-dialog>

    <el-result v-if="!course && errorMessage" icon="error" title="课程加载失败" :sub-title="errorMessage">
      <template #extra>
        <el-button type="primary" @click="loadCourse">重新加载</el-button>
      </template>
    </el-result>
  </section>
</template>
