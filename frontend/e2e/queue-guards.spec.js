import { expect, test } from '@playwright/test'
import { appendProgress, flushProgress, readProgressQueue } from '../src/utils/progressQueue.js'

test('超过200条待确认记录不截断，存储失败不覆盖已有队列', async () => {
  const values = new Map()
  let full = false
  const storage = { getItem: (key) => values.get(key), setItem: (key, value) => {
    if (full) throw new Error('QuotaExceededError')
    values.set(key, value)
  } }
  for (let i = 0; i < 250; i += 1) await appendProgress(storage, 'large', { video_id: i, watch_duration_delta: 1 })
  expect(readProgressQueue(storage, 'large')).toHaveLength(250)
  const previous = values.get('large')
  full = true
  await expect(appendProgress(storage, 'large', { video_id: 251 })).rejects.toThrow('QuotaExceededError')
  expect(values.get('large')).toBe(previous)
  full = false
  const ids = []
  expect(await flushProgress(storage, 'large', async (item) => ids.push(item.request_id), () => false)).toBe(250)
  expect(new Set(ids).size).toBe(250)
  expect(readProgressQueue(storage, 'large')).toEqual([])
})

test('真实双标签页并发新增与补传互斥，丢失响应后重用原编号', async ({ context, page }) => {
  const accepted = new Map()
  const requests = []
  let loseFirst = true
  await context.addInitScript(() => localStorage.setItem('access_token', 'isolated-queue-token'))
  await context.route(/https?:\/\/[^/]+\/api\//, async (route) => {
    const url = new URL(route.request().url())
    let data = []
    if (url.pathname === '/api/users/me') data = { id: 1, role: 'STUDENT', username: 'queue_student', real_name: '队列学生' }
    if (url.pathname === '/api/notifications') data = { items: [], unread_count: 0, pagination: { total: 0 } }
    if (url.pathname.endsWith('/progress')) {
      const payload = route.request().postDataJSON()
      requests.push(payload.request_id)
      if (!accepted.has(payload.request_id)) accepted.set(payload.request_id, payload)
      await new Promise((resolve) => setTimeout(resolve, 30))
      if (loseFirst) { loseFirst = false; await route.abort(); return }
      data = { watch_duration: accepted.size }
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ code: 200, data }) })
  })
  await page.goto('/')
  const other = await context.newPage()
  await other.goto('/')
  await Promise.all([page, other].map((tab, index) => tab.evaluate(async (index) => {
    const queue = await import('/src/utils/progressQueue.js')
    for (let n = 0; n < 20; n += 1) await queue.appendProgress(localStorage, 'cross-tab-queue', { video_id: index * 20 + n, watch_duration_delta: 1 })
  }, index)))
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('cross-tab-queue')).length)).toBe(40)
  const replay = (tab) => tab.evaluate(async () => {
    const queue = await import('/src/utils/progressQueue.js')
    return queue.flushProgress(localStorage, 'cross-tab-queue', async (item) => {
      let response
      try { response = await fetch('/api/learning/videos/1/progress', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(item) }) }
      catch { throw { status: 503 } }
      if (!response.ok) throw { status: response.status }
    }, () => false)
  })
  const running = [replay(page), replay(other)]
  await expect.poll(() => requests.length).toBeGreaterThan(0)
  // A short mutation lock permits durable enqueue while a replay holds its
  // separate network lock. The old acknowledgement must not erase this entry.
  await other.evaluate(async () => (await import('/src/utils/progressQueue.js')).appendProgress(localStorage, 'cross-tab-queue', { video_id: 999, watch_duration_delta: 1 }))
  await Promise.all(running)
  expect(accepted.size).toBe(41)
  expect(requests.length).toBe(42)
  expect(requests[0]).toBe(requests[1])
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('cross-tab-queue')).length)).toBe(0)
})

test('页头未读数量在切回窗口时刷新，失败保留旧数且过期响应不覆盖新数', async ({ page }) => {
  await page.clock.install()
  let count = 1
  let failing = false
  let slow = false
  let calls = 0
  await page.addInitScript(() => localStorage.setItem('access_token', 'isolated-message-token'))
  await page.route(/https?:\/\/[^/]+\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname
    let data = []
    if (path === '/api/users/me') data = { id: 1, role: 'STUDENT', username: 'message_student', real_name: '消息学生' }
    if (path === '/api/notifications') {
      calls += 1
      const snapshot = count
      if (slow) await new Promise((resolve) => setTimeout(resolve, 600))
      if (failing) { await route.abort(); return }
      data = { items: [], unread_count: snapshot, pagination: { total: 0 } }
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ code: 200, data }) })
  })
  await page.goto('/')
  const badge = page.locator('.nav-unread-count')
  await expect(badge).toHaveText('1')
  count = 4
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(badge).toHaveText('4')
  count = 5
  await page.clock.fastForward(31000)
  await expect(badge).toHaveText('5')
  failing = true
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(page.locator('a[title="网络异常，未读数量可能尚未更新"]')).toBeVisible()
  await expect(badge).toHaveText('5')
  failing = false
  slow = true
  count = 2
  const before = calls
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect.poll(() => calls).toBeGreaterThan(before)
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('bs-hfn:notification-count', { detail: 7 })))
  await page.waitForTimeout(700)
  await expect(badge).toHaveText('7')
})

test('课程页补传慢请求期间仍能缓存新的播放记录', async ({ page }) => {
  const puts = []
  await page.addInitScript(() => localStorage.setItem('access_token', 'isolated-learning-token'))
  await page.route(/https?:\/\/[^/]+\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname
    let data = []
    if (path === '/api/users/me') data = { id: 1, role: 'STUDENT', username: 'learning_student', real_name: '学习学生' }
    if (path === '/api/notifications') data = { items: [], unread_count: 0, pagination: { total: 0 } }
    if (path === '/api/courses/1') data = { id: 1, name: '缓存验证', status: 'PUBLISHED', teacher_id: 2, teacher_name: '教师',
      chapters: [{ id: 1, title: '章节', videos: [{ id: 1, title: '视频', status: 'READY', duration: 3, hls_url: '/media/videos/hls/e2e/index.m3u8' }] }] }
    if (path.endsWith('/state')) data = { joined: true, favorited: false }
    if (path.endsWith('/progress')) {
      data = { current_time: 0, watch_duration: 0, progress: 0 }
      if (route.request().method() === 'PUT') {
        const payload = route.request().postDataJSON()
        puts.push(payload)
        if (puts.length === 1) await new Promise((resolve) => setTimeout(resolve, 2200))
        data = { ...data, current_time: payload.current_time }
      }
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ code: 200, data }) })
  })
  await page.goto('/courses/1')
  const video = page.locator('video')
  await expect.poll(() => video.evaluate((element) => element.duration)).toBeGreaterThan(2)
  await video.evaluate((element) => { element.currentTime = 0.6; element.dispatchEvent(new Event('timeupdate')); element.dispatchEvent(new Event('pause')) })
  await expect.poll(() => puts.length).toBe(1)
  await video.evaluate((element) => { element.currentTime = 1.7; element.dispatchEvent(new Event('timeupdate')); element.dispatchEvent(new Event('pause')) })
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('bs-hfn:progress-queue:1')).length)).toBe(2)
  await expect.poll(() => puts.length).toBe(2)
  expect(puts[0].request_id).not.toBe(puts[1].request_id)
  expect(puts[0].current_time).toBeCloseTo(0.6, 1)
  expect(puts[1].current_time).toBeCloseTo(1.7, 1)
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('bs-hfn:progress-queue:1')).length)).toBe(0)
})

test('旧请求去重响应不使页面进度倒退，补传后读取服务端最新值', async ({ page }) => {
  let puts = 0
  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'isolated-learning-token')
    localStorage.setItem('bs-hfn:progress-queue:1', JSON.stringify([{ queue_id: 'old-receipt', video_id: 1,
      current_time: 20, watch_duration_delta: 10 }]))
  })
  await page.route(/https?:\/\/[^/]+\/api\//, async (route) => {
    const path = new URL(route.request().url()).pathname
    let data = []
    if (path === '/api/users/me') data = { id: 1, role: 'STUDENT', username: 'progress_student', real_name: '进度学生' }
    if (path === '/api/notifications') data = { items: [], unread_count: 0, pagination: { total: 0 } }
    if (path === '/api/courses/1') data = { id: 1, name: '历史进度', status: 'PUBLISHED', teacher_id: 2, teacher_name: '教师',
      chapters: [{ id: 1, title: '章节', videos: [{ id: 1, title: '视频', status: 'READY', duration: 100 }] }] }
    if (path.endsWith('/state')) data = { joined: true, favorited: false }
    if (path.endsWith('/progress')) {
      if (route.request().method() === 'PUT') { puts += 1; data = { current_time: 20, progress: 20, status: 'LEARNING' } }
      else data = { current_time: 80, progress: 80, status: 'LEARNING' }
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ code: 200, data }) })
  })
  await page.goto('/courses/1')
  await expect.poll(() => puts).toBe(1)
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('bs-hfn:progress-queue:1')).length)).toBe(0)
  await expect(page.getByText('80%', { exact: true })).toBeVisible()
  await expect(page.getByText('20%', { exact: true })).toHaveCount(0)
})

for (const role of ['STUDENT', 'TEACHER']) {
  for (const width of [1440, 390]) {
    test(`统计口径说明与长文本布局 ${role} ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 750 })
      await page.addInitScript(() => localStorage.setItem('access_token', 'isolated-statistics-token'))
      await page.route(/https?:\/\/[^/]+\/api\//, async (route) => {
        const path = new URL(route.request().url()).pathname
        let data = []
        if (path === '/api/users/me') data = { id: 1, role, username: 'statistics_user', real_name: '统计用户' }
        if (path === '/api/notifications') data = { items: [], unread_count: 0, pagination: { total: 0 } }
        if (path === '/api/statistics') data = { joined_courses: 3, published_joined_courses: 1, watch_duration_seconds: 7200, ready_videos: 12 }
        if (path === '/api/statistics/courses') data = [{ course_name: '长课程名称'.repeat(15), status: 'OFFLINE', student_count: 2, ready_video_count: 4, average_progress: 30, average_homework_percent: 80, average_exam_percent: 90 }]
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ code: 200, data }) })
      })
      await page.goto('/statistics')
      await expect(page.locator('.statistics-grid')).toBeVisible()
      await expect(page.locator('.statistics-page > .dialog-tip')).toContainText(role === 'STUDENT' ? '当前可学习课程 1 门' : '当前在册学生')
      await page.screenshot({ path: `test-results/statistics-${role}-${width}.png` })
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    })
  }
}
