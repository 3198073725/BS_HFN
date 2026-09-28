<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({ text: { type: [String, Number], default: '' }, label: { type: String, default: '查看全文' } })
const value = ref(null)
const truncated = ref(false)
let observer
let alive = true
function measure() {
  if (alive && value.value) truncated.value = value.value.scrollWidth > value.value.clientWidth + 1
}
onMounted(() => { observer = new ResizeObserver(measure); observer.observe(value.value); measure() })
watch(() => props.text, async () => { await nextTick(); measure() })
onBeforeUnmount(() => { alive = false; observer?.disconnect() })
</script>

<template>
  <div class="overflow-text">
    <div ref="value" class="overflow-text-value" :title="String(text ?? '')">{{ text === '' || text == null ? '—' : text }}</div>
    <details v-if="truncated" class="overflow-text-details">
      <summary :aria-label="label">全文</summary>
      <div class="overflow-text-full" tabindex="0" :aria-label="label">{{ text }}</div>
    </details>
  </div>
</template>

<style scoped>
.overflow-text { min-width: 0; width: 100%; }
.overflow-text-value { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.overflow-text-details { margin-top: 4px; font-size: 12px; line-height: 1.6; color: var(--ink-600); }
.overflow-text-details summary { cursor: pointer; width: fit-content; }
.overflow-text-full { max-height: 180px; overflow: auto; overscroll-behavior: contain; overflow-wrap: anywhere; white-space: pre-wrap; padding: 8px; margin-top: 4px; border: 1px solid var(--line); border-radius: 4px; background: #f7f8f9; }
.overflow-text-details summary:focus-visible, .overflow-text-full:focus-visible { outline: 2px solid var(--ink-600); outline-offset: 2px; }
</style>
