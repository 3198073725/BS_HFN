<script setup>
import Hls from 'hls.js/light'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'


const props = defineProps({
  source: { type: String, required: true },
  startTime: { type: Number, default: 0 },
})
const emit = defineEmits(['timeupdate', 'checkpoint'])

const videoElement = ref(null)
let hls = null

function loadSource() {
  if (!videoElement.value || !props.source) return
  hls?.destroy()
  hls = null
  videoElement.value.removeAttribute('src')
  videoElement.value.load()
  if (Hls.isSupported()) {
    hls = new Hls()
    hls.loadSource(props.source)
    hls.attachMedia(videoElement.value)
  } else if (videoElement.value.canPlayType('application/vnd.apple.mpegurl')) {
    videoElement.value.src = props.source
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
  <video
    ref="videoElement"
    class="video-player"
    controls
    playsinline
    preload="metadata"
    @loadedmetadata="applyStartTime"
    @timeupdate="reportTime"
    @pause="checkpoint"
    @ended="checkpoint"
  />
</template>

<style scoped>
.video-player {
  display: block;
  width: 100%;
  max-height: 72vh;
  background: #000;
}
</style>
