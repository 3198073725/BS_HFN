<script setup>
import Hls from 'hls.js/light'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'


const props = defineProps({
  source: { type: String, required: true },
  startTime: { type: Number, default: 0 },
})
const emit = defineEmits(['timeupdate', 'checkpoint'])

const videoElement = ref(null)
const playbackError = ref('')
let hls = null
let mediaRecoveryAttempts = 0

function showPlaybackError(message) {
  playbackError.value = message
  hls?.destroy()
  hls = null
}

function handleHlsError(_event, data) {
  if (!data.fatal) return
  if (data.type === Hls.ErrorTypes.MEDIA_ERROR && mediaRecoveryAttempts < 1) {
    mediaRecoveryAttempts += 1
    hls?.recoverMediaError()
    return
  }
  const message = data.type === Hls.ErrorTypes.NETWORK_ERROR
    ? '视频资源暂时无法加载，请检查网络后重试'
    : '视频暂时无法播放，请稍后重试'
  showPlaybackError(message)
}

function loadSource() {
  if (!videoElement.value || !props.source) return
  playbackError.value = ''
  mediaRecoveryAttempts = 0
  hls?.destroy()
  hls = null
  videoElement.value.removeAttribute('src')
  videoElement.value.load()
  if (Hls.isSupported()) {
    hls = new Hls()
    hls.on(Hls.Events.ERROR, handleHlsError)
    hls.loadSource(props.source)
    hls.attachMedia(videoElement.value)
  } else if (videoElement.value.canPlayType('application/vnd.apple.mpegurl')) {
    videoElement.value.src = props.source
  } else {
    showPlaybackError('当前浏览器不支持该视频格式')
  }
}

function handleNativeError() {
  if (!hls && !playbackError.value) {
    showPlaybackError('视频资源暂时无法加载，请检查网络后重试')
  }
}

function applyStartTime() {
  if (!videoElement.value || props.startTime <= 0) return
  const duration = Number.isFinite(videoElement.value.duration) ? videoElement.value.duration : props.startTime
  videoElement.value.currentTime = Math.min(props.startTime, Math.max(duration - 1, 0))
}

function reportTime() {
  emit('timeupdate', videoElement.value?.currentTime || 0)
}

function checkpoint() {
  emit('checkpoint', videoElement.value?.currentTime || 0)
}

onMounted(loadSource)
watch(() => props.source, loadSource)
watch(() => props.startTime, (value) => {
  if (value > 0 && (videoElement.value?.currentTime || 0) < 2) applyStartTime()
})
onBeforeUnmount(() => hls?.destroy())

defineExpose({
  getCurrentTime: () => videoElement.value?.currentTime || 0,
  seekTo: (seconds) => {
    if (!videoElement.value) return
    const duration = Number(videoElement.value.duration || 0)
    videoElement.value.currentTime =
      duration > 0 ? Math.min(Math.max(seconds, 0), duration) : Math.max(seconds, 0)
  },
})
</script>

<template>
  <div class="video-player-shell">
    <video
      ref="videoElement"
      v-show="!playbackError"
      class="video-player"
      controls
      playsinline
      preload="metadata"
      @error="handleNativeError"
      @loadedmetadata="applyStartTime"
      @timeupdate="reportTime"
      @pause="checkpoint"
      @ended="checkpoint"
    />
    <div v-if="playbackError" class="video-player-error" role="alert">
      <span aria-hidden="true">!</span>
      <strong>{{ playbackError }}</strong>
      <button type="button" @click="loadSource">重新加载视频</button>
    </div>
  </div>
</template>

<style scoped>
.video-player-shell {
  position: relative;
  min-height: 260px;
  overflow: hidden;
  background: #05070b;
}

.video-player {
  display: block;
  width: 100%;
  max-height: 72vh;
  background: #000;
}

.video-player-error {
  display: grid;
  min-height: 260px;
  padding: 28px;
  place-items: center;
  align-content: center;
  gap: 12px;
  background: radial-gradient(circle at 50% 25%, #202a3b 0, #080b12 65%);
  color: #fff;
  text-align: center;
}

.video-player-error > span {
  display: grid;
  width: 42px;
  height: 42px;
  border: 1px solid rgb(255 255 255 / 24%);
  border-radius: 50%;
  place-items: center;
  color: #ffbd66;
  font-size: 22px;
  font-weight: 800;
}

.video-player-error strong {
  font-size: 14px;
}

.video-player-error button {
  padding: 9px 16px;
  border: 1px solid rgb(255 255 255 / 28%);
  border-radius: 9px;
  background: rgb(255 255 255 / 10%);
  color: #fff;
  cursor: pointer;
}

.video-player-error button:hover {
  background: rgb(255 255 255 / 18%);
}
</style>
