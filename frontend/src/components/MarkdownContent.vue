<script setup>
import { computed } from 'vue'
import { renderMarkdown } from '../utils/markdown'

const props = defineProps({ content: { type: String, default: '' } })
const html = computed(() => renderMarkdown(props.content))
</script>

<template>
  <div class="markdown-content" v-html="html" />
</template>

<style scoped>
.markdown-content { min-width: 0; max-width: 100%; color: var(--ink-900, #243746); line-height: 1.85; overflow-wrap: anywhere; }
.markdown-content :deep(> :first-child) { margin-top: 0; }
.markdown-content :deep(> :last-child) { margin-bottom: 0; }
.markdown-content :deep(h1), .markdown-content :deep(h2), .markdown-content :deep(h3),
.markdown-content :deep(h4), .markdown-content :deep(h5), .markdown-content :deep(h6) { margin: 1.4em 0 .65em; font-weight: 650; line-height: 1.5; }
.markdown-content :deep(h1) { font-size: 1.6em; }
.markdown-content :deep(h2) { padding-bottom: .4em; border-bottom: 1px solid var(--line, #dbe2e8); font-size: 1.35em; }
.markdown-content :deep(h3) { font-size: 1.15em; }
.markdown-content :deep(h4), .markdown-content :deep(h5), .markdown-content :deep(h6) { font-size: 1em; }
.markdown-content :deep(p) { margin: .75em 0; }
.markdown-content :deep(ul), .markdown-content :deep(ol) { margin: .75em 0; padding-left: 1.8em; }
.markdown-content :deep(ul) { list-style: disc; }
.markdown-content :deep(ol) { list-style: decimal; }
.markdown-content :deep(li) { margin: .3em 0; }
.markdown-content :deep(li > ul), .markdown-content :deep(li > ol) { margin: .3em 0; }
.markdown-content :deep(strong) { font-weight: 700; }
.markdown-content :deep(a) { color: var(--el-color-primary, #285c80); text-decoration: underline; text-underline-offset: 3px; }
.markdown-content :deep(blockquote) { margin: 1em 0; padding: .25em 1em; border-left: 3px solid #b6c8d5; color: var(--ink-600, #607486); background: #f7f9fb; }
.markdown-content :deep(code) { padding: .15em .35em; border-radius: 3px; background: #eef2f5; font-family: Consolas, 'Courier New', monospace; font-size: .9em; }
.markdown-content :deep(pre) { max-width: 100%; margin: 1em 0; padding: 16px; overflow: auto; border: 1px solid var(--line, #dbe2e8); border-radius: 6px; background: #f6f8fa; line-height: 1.6; white-space: pre; overflow-wrap: normal; }
.markdown-content :deep(pre code) { padding: 0; border: 0; background: transparent; white-space: inherit; }
.markdown-content :deep(.markdown-table) { max-width: 100%; margin: 1em 0; overflow-x: auto; }
.markdown-content :deep(table) { width: 100%; border-collapse: collapse; font-size: .95em; }
.markdown-content :deep(th), .markdown-content :deep(td) { padding: 10px 14px; border: 1px solid var(--line, #dbe2e8); text-align: left; }
.markdown-content :deep(th) { background: #f2f5f7; font-weight: 600; }
.markdown-content :deep(hr) { margin: 1.5em 0; border: 0; border-top: 1px solid var(--line, #dbe2e8); }
.markdown-content :deep(img) { max-width: 100%; height: auto; }
@media (max-width: 620px) {
  .markdown-content :deep(pre) { padding: 12px; }
  .markdown-content :deep(th), .markdown-content :deep(td) { padding: 8px; }
}
</style>
