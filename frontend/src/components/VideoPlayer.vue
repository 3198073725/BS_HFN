<script setup>
import Hls from 'hls.js'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'


const props = defineProps({
  source: { type: String, required: true },
})

const videoElement = ref(null)
let hls = null

function loadSource() {
  if (!videoElement.value || !props.source) return
  if (Hls.isSupported()) {
    hls?.destroy()
    hls = new Hls()
    hls.loadSource(props.source)
    hls.attachMedia(videoElement.value)
  } else if (videoElement.value.canPlayType('application/vnd.apple.mpegurl')) {
    videoElement.value.src = props.source
  }
}

onMounted(loadSource)
watch(() => props.source, loadSource)
onBeforeUnmount(() => hls?.destroy())
</script>

<template>
  <video ref="videoElement" class="video-player" controls playsinline />
</template>

<style scoped>
.video-player {
  display: block;
  width: 100%;
  max-height: 72vh;
  background: #000;
}
</style>
