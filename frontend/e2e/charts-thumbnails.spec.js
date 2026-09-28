import { expect, test } from '@playwright/test'
import { resolve } from 'node:path'

const errors = new WeakMap()
test.beforeEach(({ page }) => {
  const list = []
  errors.set(page, list)
  page.on('pageerror', (error) => list.push(error.message))
})
test.afterEach(({ page }) => { expect(errors.get(page)).toEqual([]) })
async function isolate(page, role, handler = () => null) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'isolated-chart-test'))
  await page.route(/https?:\/\/[^/]+\/api\//, async (route) => {
    const url = new URL(route.request().url())
    const response = await handler(url) || {}
    const fallback = url.pathname === '/api/users/me' ? { id: 1, role, real_name: '图表测试用户' }
      : url.pathname.includes('/notifications') ? { items: [], unread_count: 0, pagination: { total: 0 } }
        : ['/api/admin/videos', '/api/admin/users', '/api/admin/courses', '/api/admin/audit-logs'].includes(url.pathname)
          ? { items: [], summary: {}, runtime: {}, pagination: { total: 0 } }
          : url.pathname === '/api/statistics' ? {} : []
    await route.fulfill({ status: response.status || 200, contentType: 'application/json',
      body: JSON.stringify({ code: response.status || 200, message: response.message || 'OK', data: response.data ?? fallback }) })
  })
}
async function noOverflow(page) {
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
}
const chart = (page, title) => page.locator('.statistics-chart').filter({ has: page.getByRole('heading', { name: title, exact: true }) })
const studentOverview = { joined_courses: 6, published_joined_courses: 5, learned_videos: 12, completed_videos: 4,
  average_video_progress: 62.5, watch_duration_seconds: 3600, submitted_homeworks: 7, graded_homeworks: 3,
  average_homework_percent: 85, completed_exams: 2, average_exam_percent: 75 }
const courses = (total) => Array.from({ length: total }, (_, i) => ({ course_id: i + 1,
  course_name: `课程${i + 1}-${'连续英文长名称'.repeat(12)}`, status: ['PUBLISHED', 'DRAFT', 'OFFLINE'][i % 3],
  student_count: 10, ready_video_count: 4, average_progress: i % 101,
  average_homework_percent: 80, average_exam_percent: 65 }))

for (const width of [390, 1440]) {
  test(`学生ECharts真实SVG与数据表使用相同统计值-${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 })
    await isolate(page, 'STUDENT', (url) => url.pathname === '/api/statistics' ? { data: studentOverview } : null)
    await page.goto('/statistics')
    await expect(page.locator('.statistics-chart-canvas svg')).toHaveCount(2)
    const percent = chart(page, '学习与成绩概览')
    await expect(percent.locator('svg')).toContainText('62.5%')
    await percent.locator('summary').click()
    await expect(percent.getByRole('row').filter({ hasText: '作业平均得分率' })).toContainText('85%')
    const counts = chart(page, '累计学习与任务记录')
    await counts.locator('summary').click()
    await expect(counts.getByRole('row').filter({ hasText: '已批改作业' })).toContainText('3')
    await noOverflow(page)
    await page.screenshot({ path: resolve(`../output/audit-20260913/学生ECharts-${width}.png`), fullPage: true })
    await page.setViewportSize({ width: width === 390 ? 1440 : 390, height: 960 })
    await expect.poll(async () => percent.locator('svg').evaluate((svg) => Math.abs(Number(svg.getAttribute('width')) - svg.parentElement.clientWidth))).toBeLessThan(1)
    await noOverflow(page)
  })

  test(`40门课程图表按6项分页且长名称有全文数据入口-${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 })
    await isolate(page, 'TEACHER', (url) => url.pathname === '/api/statistics/courses' ? { data: courses(40) }
      : url.pathname === '/api/statistics' ? { data: { courses: 40, published_courses: 14 } } : null)
    await page.goto('/statistics')
    const comparison = chart(page, '课程学习与成绩对比')
    await expect(comparison.locator('.statistics-chart-canvas svg')).toBeVisible()
    await comparison.locator('summary').click()
    await expect(comparison.locator('tbody tr')).toHaveCount(6)
    await expect(comparison.locator('tbody')).toContainText(courses(40)[0].course_name)
    const pager = comparison.locator('.el-pagination')
    const firstPageY = await pager.evaluate((element) => element.getBoundingClientRect().top + window.scrollY)
    await comparison.getByRole('button', { name: '下一页', exact: true }).click()
    await expect(comparison.locator('tbody')).toContainText(courses(40)[6].course_name)
    await expect(comparison.locator('tbody')).not.toContainText(courses(40)[0].course_name)
    await comparison.getByRole('listitem', { name: '第 7 页', exact: true }).click()
    await expect(comparison.locator('tbody tr')).toHaveCount(4)
    const lastPageY = await pager.evaluate((element) => element.getBoundingClientRect().top + window.scrollY)
    expect(Math.abs(lastPageY - firstPageY)).toBeLessThan(1)
    const states = chart(page, '课程发布状态')
    await states.locator('summary').click()
    await expect(states.getByRole('row').filter({ hasText: '已发布' })).toContainText('14门')
    await noOverflow(page)
    expect((await comparison.boundingBox()).height).toBeLessThan(1050)
    await page.screenshot({ path: resolve(`../output/audit-20260913/教师ECharts-${width}.png`), fullPage: true })
    await page.goto('/courses')
    await expect(page.locator('.statistics-chart-canvas')).toHaveCount(0)
    await page.goto('/statistics')
    await expect(page.locator('.statistics-chart-canvas svg')).toHaveCount(2)
  })

  test(`管理员图表默认折叠并使用全局计数和中性色-${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 })
    await isolate(page, 'ADMIN', (url) => url.pathname === '/api/statistics' ? { data: {
      users: 26, students: 20, teachers: 5, administrators: 1, ready_videos: 30, processing_videos: 2, failed_videos: 3,
    } } : null)
    await page.goto('/admin')
    await expect(page.locator('.el-loading-mask:visible')).toHaveCount(0)
    await expect(page.locator('.statistics-chart-canvas')).toHaveCount(0)
    await page.getByText('查看数据图表', { exact: true }).click()
    await expect(page.locator('.statistics-chart-canvas svg')).toHaveCount(2)
    const accounts = chart(page, '用户角色分布')
    await accounts.locator('summary').click()
    await expect(accounts.getByRole('row').filter({ hasText: '学生' })).toContainText('20人')
    const videos = chart(page, '视频处理状态分布')
    await expect(videos.locator('svg')).toContainText('30个')
    expect(await videos.locator('svg path').evaluateAll((paths) => paths.some((path) => path.getAttribute('fill') === '#555b61'))).toBe(true)
    await noOverflow(page)
    await page.getByText('查看数据图表', { exact: true }).click()
    await expect(page.locator('.statistics-chart-canvas')).toHaveCount(0)
    await page.getByText('查看数据图表', { exact: true }).click()
    await expect(page.locator('.statistics-chart-canvas svg')).toHaveCount(2)
  })
}

test('统计无数据、加载失败及刷新恢复不显示虚构图表', async ({ page }) => {
  let state = 'error'
  await isolate(page, 'STUDENT', (url) => url.pathname === '/api/statistics'
    ? state === 'error' ? { status: 500, message: '统计暂不可用' } : { data: state === 'empty' ? {} : studentOverview } : null)
  await page.goto('/statistics')
  await expect(page.getByText('统计数据加载失败', { exact: true })).toBeVisible()
  await expect(page.locator('.statistics-chart-canvas')).toHaveCount(0)
  state = 'empty'
  await page.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.getByText('暂无可展示的统计数据', { exact: true })).toHaveCount(2)
  await expect(page.locator('.statistics-chart-canvas')).toHaveCount(0)
  state = 'data'
  await page.getByRole('button', { name: '刷新数据', exact: true }).click()
  await expect(page.locator('.statistics-chart-canvas svg')).toHaveCount(2)
})

for (const width of [390, 1440]) {
  test(`已加入与收藏横向缩略图等大、完整显示且损坏图回退-${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 })
    await page.route('**/thumbnail-wide.svg', (route) => route.fulfill({ contentType: 'image/svg+xml',
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900"><rect width="1600" height="900" fill="#eee"/><text x="50" y="450" font-size="120">完整封面</text></svg>' }))
    await page.route('**/thumbnail-broken.png', (route) => route.fulfill({ status: 404, body: '' }))
    const data = [{ id: 1, name: '横向封面课程', cover_url: '/thumbnail-wide.svg', learning_progress: 50, description: '横向课程封面完整显示。' },
      { id: 2, name: '损坏封面课程', cover_url: '/thumbnail-broken.png', learning_progress: 0 },
      { id: 3, name: '无封面课程', cover_url: '', learning_progress: 0 }]
    await isolate(page, 'STUDENT', (url) => ['/api/learning/courses', '/api/learning/favorites'].includes(url.pathname) ? { data } : null)
    await page.goto('/learning')
    const panel = page.getByRole('tabpanel', { name: '已加入' })
    const image = panel.getByRole('img', { name: '横向封面课程封面' })
    await expect.poll(() => image.evaluate((img) => img.naturalWidth)).toBe(1600)
    expect(await image.evaluate((img) => getComputedStyle(img).objectFit)).toBe('contain')
    const mark = panel.locator('.course-thumbnail').first()
    const before = await mark.boundingBox()
    expect(before.width / before.height).toBeCloseTo(1.6, 1)
    await expect(panel.locator('.course-thumbnail').nth(1).locator('img')).toHaveCount(0)
    await expect(panel.locator('.course-thumbnail').nth(1)).toHaveText('损')
    await expect(panel.locator('.course-thumbnail').nth(2)).toHaveText('无')
    const cardHeight = (await panel.locator('.learning-course-card').first().boundingBox()).height
    await page.getByRole('tab', { name: /我的收藏/ }).click()
    const favoritePanel = page.getByRole('tabpanel', { name: '我的收藏' })
    const after = await favoritePanel.locator('.course-thumbnail').first().boundingBox()
    expect(after.width).toBeCloseTo(before.width, 1)
    expect(after.height).toBeCloseTo(before.height, 1)
    expect((await favoritePanel.locator('.learning-course-card').first().boundingBox()).height).toBeCloseTo(cardHeight, 1)
    await noOverflow(page)
    await page.screenshot({ path: resolve(`../output/audit-20260913/学习缩略图-${width}.png`), fullPage: true })
  })
}
