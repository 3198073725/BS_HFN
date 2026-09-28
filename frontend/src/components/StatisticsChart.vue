<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { init, use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'

use([BarChart, AriaComponent, GridComponent, LegendComponent, TooltipComponent, SVGRenderer])

const props = defineProps({
  title: { type: String, required: true },
  caption: { type: String, default: '' },
  rows: { type: Array, default: () => [] },
  series: { type: Array, default: () => [] },
  percentage: { type: Boolean, default: false },
  unit: { type: String, default: '' },
  neutral: { type: Boolean, default: false },
})
const host = ref(null)
const currentPage = ref(1)
const pageSize = 6
const number = (value) => Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0
const hasData = computed(() => props.rows.some((row) => row.values.some((value) => number(value) > 0)))
const visibleRows = computed(() => props.rows.slice((currentPage.value - 1) * pageSize, currentPage.value * pageSize))
const suffix = computed(() => props.percentage ? '%' : props.unit)
// A paginated chart reserves a full page of plotting space. Otherwise the
// pager jumps upward when the final page contains fewer rows.
const chartRowSlots = computed(() => props.rows.length > pageSize ? pageSize : visibleRows.value.length)
const height = computed(() => Math.max(250, 90 + chartRowSlots.value * (props.series.length > 1 ? 62 : 38)))
let chart
let observer
let frame
let alive = true

function resize() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(() => {
    if (alive && chart && host.value?.clientWidth) chart.resize()
  })
}

async function render() {
  await nextTick()
  if (!alive) return
  if (!hasData.value || !host.value) {
    observer?.disconnect()
    chart?.dispose()
    chart = null
    return
  }
  if (!chart) {
    chart = init(host.value, null, { renderer: 'svg' })
    observer = new ResizeObserver(resize)
    observer.observe(host.value)
  }
  chart.setOption({
    animation: false,
    color: props.neutral ? ['#555b61', '#8c9297', '#bac0c4'] : ['#496b80', '#879d9f', '#b4bdc8'],
    textStyle: { fontFamily: 'Microsoft YaHei, sans-serif', color: '#526576', fontSize: 12 },
    aria: { enabled: true, label: { description: `${props.title}。完整数值可展开下方数据表查看。` } },
    tooltip: { trigger: 'axis', renderMode: 'richText', confine: true, valueFormatter: (value) => `${value}${suffix.value}` },
    legend: { show: props.series.length > 1, top: 8, itemWidth: 12, itemHeight: 8 },
    grid: { left: 116, right: 40, top: props.series.length > 1 ? 48 : 24, bottom: 30 },
    xAxis: { type: 'value', min: 0, max: props.percentage ? 100 : undefined, minInterval: props.percentage ? undefined : 1,
      axisLabel: { formatter: props.percentage ? '{value}%' : '{value}' }, splitLine: { lineStyle: { color: '#e9edf0' } } },
    yAxis: { type: 'category', inverse: true, data: visibleRows.value.map((row) => row.label),
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { width: 100, overflow: 'truncate' } },
    series: props.series.map((name, index) => ({ name, type: 'bar', barMaxWidth: 16,
      data: visibleRows.value.map((row) => number(row.values[index])),
      label: { show: props.series.length === 1, position: 'right', formatter: (item) => `${item.value}${suffix.value}` } })),
  }, { notMerge: true })
  chart.resize()
}

watch(() => props.rows.length, (total) => { currentPage.value = Math.min(currentPage.value, Math.max(1, Math.ceil(total / pageSize))) })
watch([() => props.rows, () => props.series, () => props.percentage, () => props.neutral, () => props.unit, currentPage], render, { deep: true, flush: 'post' })
onMounted(render)
onBeforeUnmount(() => { alive = false; observer?.disconnect(); cancelAnimationFrame(frame); chart?.dispose() })
</script>

<template>
  <section class="statistics-chart" :aria-label="title">
    <header><h2>{{ title }}</h2><p>{{ caption }}</p></header>
    <div v-if="hasData" ref="host" class="statistics-chart-canvas" :style="{ height: `${height}px` }" role="img" :aria-label="`${title}，下方提供完整数值表`" />
    <el-empty v-else description="暂无可展示的统计数据" :image-size="58" class="chart-empty" />
    <el-pagination v-if="rows.length > pageSize" v-model:current-page="currentPage" small layout="prev, pager, next"
      :page-size="pageSize" :total="rows.length" :aria-label="`${title}分页`" />
    <details class="chart-data">
      <summary>查看图表数据{{ rows.length > pageSize ? `（第${currentPage}页，共${rows.length}项）` : '' }}</summary>
      <div class="chart-data-scroll" tabindex="0" :aria-label="`${title}完整数值`">
        <table><caption>{{ title }}{{ suffix ? `（${suffix}）` : '' }}</caption>
          <thead><tr><th scope="col">指标 / 课程</th><th v-for="name in series" :key="name" scope="col">{{ name }}</th></tr></thead>
          <tbody><tr v-for="(row, index) in visibleRows" :key="index"><th scope="row">{{ row.label }}</th>
            <td v-for="(_name, i) in series" :key="i">{{ number(row.values[i]) }}{{ suffix }}</td></tr></tbody>
        </table>
      </div>
    </details>
  </section>
</template>

<style scoped>
.statistics-chart { min-width: 0; padding: 20px; border: 1px solid var(--line); border-radius: 9px; background: #fff; }
header h2 { margin: 0; color: var(--ink-900); font-size: 16px; }
header p { margin: 7px 0 0; color: var(--ink-600); font-size: 12px; line-height: 1.7; }
.statistics-chart-canvas { width: 100%; min-width: 0; }
.chart-empty { min-height: 250px; }
.chart-data { margin-top: 10px; color: var(--ink-600); font-size: 12px; }
.chart-data summary { cursor: pointer; padding: 5px 0; }
.chart-data-scroll { max-height: 240px; overflow: auto; margin-top: 8px; }
table { width: 100%; border-collapse: collapse; color: var(--ink-900); }
caption { text-align: left; padding: 8px 0; }
th, td { text-align: left; padding: 9px; border-bottom: 1px solid var(--line); overflow-wrap: anywhere; }
td { white-space: nowrap; }
.el-pagination { justify-content: center; margin: 8px 0; max-width: 100%; flex-wrap: wrap; }
@media (max-width: 600px) { .statistics-chart { padding: 14px; } }
</style>
