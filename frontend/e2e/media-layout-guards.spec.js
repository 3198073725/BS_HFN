import { expect, test } from '@playwright/test'
import { appendProgress, flushProgress, readProgressQueue } from '../src/utils/progressQueue.js'

test('暂不可学习的队列项保留但不阻挡其他视频，删除项明确通知且不中断补传', async () => {
  const values = new Map()
  const storage = { getItem: (key) => values.get(key), setItem: (key, value) => values.set(key, value) }
  for (const video_id of [1, 2, 3, 4]) await appendProgress(storage, 'media', { video_id })
  const original = readProgressQueue(storage, 'media')[0]
  const calls = [], discarded = []
  expect(await flushProgress(storage, 'media', async (item) => {
    calls.push(item.video_id)
    if (item.video_id === 1) throw { status: 423 }
    if (item.video_id === 2) throw { status: 404 }
  }, () => false, (item) => discarded.push(item.video_id))).toBe(2)
  expect(calls).toEqual([1, 2, 3, 4])
  expect(discarded).toEqual([2])
  expect(readProgressQueue(storage, 'media')).toEqual([original])
  const recovered = []
  expect(await flushProgress(storage, 'media', async (item) => recovered.push(item.request_id), () => false)).toBe(1)
  expect(recovered).toEqual([original.request_id])
})

async function isolate(page, user, handler) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'isolated-media-layout'))
  await page.route(/https?:\/\/[^/]+\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname
    const result = await handler(path, route.request())
    const status = result?.httpStatus || 200
    const data = (result?.httpStatus ? result.data : result) ?? (path === '/api/users/me' ? user
      : path === '/api/notifications' ? { items: [], unread_count: 0, pagination: { total: 0 } } : [])
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ code: status, data }) })
  })
}

test('课程页明确提示失效旧记录，保留暂不可学习项，恢复联网后原编号补传', async ({ page }) => {
  let unavailable = true
  const requests = []
  await page.addInitScript(() => localStorage.setItem('bs-hfn:progress-queue:1', JSON.stringify(
    [1, 2, 3].map((video_id) => ({ video_id, current_time: 10, watch_duration_delta: 5,
      queue_id: `media-${video_id}`, request_id: `media-${video_id}` })),
  )))
  await isolate(page, { id: 1, role: 'STUDENT', real_name: '测试学生' }, (path, request) => {
    if (path === '/api/courses/1') return { id: 1, name: '补传测试课程', teacher_id: 2, status: 'PUBLISHED',
      chapters: [{ id: 1, title: '第一章', videos: [{ id: 3, title: '当前视频', status: 'READY', duration: 100 }] }] }
    if (path.endsWith('/state')) return { joined: true, favorited: false }
    if (path.endsWith('/progress') && request.method() === 'PUT') {
      requests.push(request.postDataJSON().request_id)
      if (path.includes('/videos/1/') && unavailable) return { httpStatus: 423 }
      if (path.includes('/videos/2/')) return { httpStatus: 404 }
      return { progress: 10, current_time: 10, watch_duration: 5 }
    }
    if (path.endsWith('/progress')) return { progress: 10, current_time: 10, watch_duration: 5 }
  })
  await page.goto('/courses/1')
  await expect(page.locator('.el-message--warning')).toContainText('1 条旧进度无法补传')
  await expect(page.locator('.offline-progress-chip')).toContainText('1 条进度待补传')
  expect(requests).toEqual(['media-1', 'media-2', 'media-3'])
  unavailable = false
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await expect(page.locator('.offline-progress-chip')).toHaveCount(0)
  expect(requests).toEqual(['media-1', 'media-2', 'media-3', 'media-1'])
})

test('40个班级仅有一个Tab入口，方向键和首尾键切换并在列表内滚动', async ({ page }) => {
  const classes = Array.from({ length: 40 }, (_, n) => ({ id: n + 1, name: `班级${n + 1}-${'长名称'.repeat(20)}`,
    description: '班级说明', member_count: 0, course_count: 0, students: [], courses: [] }))
  await isolate(page, { id: 1, role: 'TEACHER', real_name: '测试老师' }, (path) => {
    if (path === '/api/classes') return classes
    if (path.startsWith('/api/statistics/classes/')) return { overview: {}, courses: [], students: [] }
  })
  await page.goto('/classes')
  const options = page.getByRole('option')
  await expect(options).toHaveCount(40)
  await expect(page.locator('.classroom-list [tabindex="0"]')).toHaveCount(1)
  await options.first().focus()
  await page.keyboard.press('ArrowDown')
  await expect(options.nth(1)).toBeFocused()
  await expect(options.nth(1)).toHaveAttribute('aria-selected', 'true')
  await page.keyboard.press('End')
  await expect(options.last()).toBeFocused()
  await expect(options.last()).toHaveAttribute('aria-selected', 'true')
  expect(await page.locator('.classroom-list').evaluate((el) => el.scrollTop)).toBeGreaterThan(0)
  await page.keyboard.press('Home')
  await expect(options.first()).toBeFocused()
  await page.getByPlaceholder('搜索班级名称或说明').fill('班级25-')
  await expect(options).toHaveCount(1)
  await expect(options.first()).toHaveAttribute('tabindex', '0')
  await expect(options.first()).toHaveAttribute('title', classes[24].name)
  const layout = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }))
  expect(layout.scroll).toBeLessThanOrEqual(layout.width + 1)
})

for (const width of [1440, 390]) {
  test(`视频表格长文件名与完整错误可键盘展开，20条记录不撑开页面-${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    const error = `ffmpeg: ${'无法解析源视频参数/'.repeat(100)} END-OF-ERROR`
    const original_name = `${'long-file-name-'.repeat(30)}.mp4`
    const items = Array.from({ length: 20 }, (_, n) => ({ id: n + 1, title: `视频${n + 1}`,
      original_name, course_name: '课程'.repeat(50), chapter_title: '第一章', teacher_name: '测试教师',
      status: 'FAILED', process_step: 'TRANSCODE', error_message: error, retryable: false, removable: false }))
    await isolate(page, { id: 1, role: 'ADMIN', real_name: '测试管理员' }, (path) => {
      if (path === '/api/admin/overview') return {}
      if (path === '/api/admin/videos') return { items, summary: { total: 20, FAILED: 20 }, pagination: { page: 1, page_size: 20, total: 20 } }
    })
    await page.goto('/admin')
    await expect(page.locator('.admin-video-center .el-table__body tr')).toHaveCount(20)
    const diagnostic = page.locator('.admin-cell-details').filter({ hasText: '查看错误原因' }).first()
    await diagnostic.locator('summary').focus()
    await page.keyboard.press('Enter')
    await expect(diagnostic).toHaveAttribute('open', '')
    await expect(diagnostic.locator('div')).toHaveText(error)
    expect(await diagnostic.locator('div').evaluate((el) => el.clientHeight)).toBeLessThanOrEqual(160)
    const metadata = page.locator('.admin-cell-details').filter({ hasText: '查看完整信息' }).first()
    await metadata.locator('summary').focus()
    await page.keyboard.press('Enter')
    await expect(metadata.locator('div')).toContainText(original_name)
    if (width === 390) {
      const fixed = page.locator('.admin-video-center td.el-table-fixed-column--left').first()
      await expect(fixed).toHaveCSS('position', 'static')
      await diagnostic.locator('summary').focus()
      const bounds = await diagnostic.locator('summary').boundingBox()
      expect(bounds.x).toBeGreaterThanOrEqual(0)
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(width)
    }
    const layout = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }))
    expect(layout.scroll).toBeLessThanOrEqual(layout.width + 1)
    await page.screenshot({ path: `../output/audit-20260913/修复后-长错误视频表格-${width}.png`, fullPage: true })
  })
}
