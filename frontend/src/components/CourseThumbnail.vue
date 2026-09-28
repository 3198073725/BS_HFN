<script setup>
import { ref, watch } from 'vue'

const props = defineProps({ src: { type: String, default: '' }, name: { type: String, default: '' } })
const failed = ref(false)
watch(() => props.src, () => { failed.value = false })
</script>

<template>
  <div class="course-thumbnail">
    <img v-if="src && !failed" :src="src" :alt="`${name || '课程'}封面`" loading="lazy" @error="failed = true" />
    <span v-else aria-hidden="true">{{ name?.slice(0, 1) || '课' }}</span>
  </div>
</template>

<style scoped>
.course-thumbnail { overflow: hidden; background: #f3f5f6; }
.course-thumbnail img { display: block; width: 100%; height: 100%; object-fit: contain; }
</style>
