import { expect, test } from '@playwright/test'

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
async function isolate(page, role, handler) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'isolated-interaction'))
  await page.route(/https?:\/\/[^/]+\/api\//, async (route) => {
    const request = route.request()
    const result = await handler(new URL(request.url()), request) || {}
    const data = result.data ?? (request.url().includes('/api/users/me')
      ? { id: 1, role, real_name: '测试用户' }
      : request.url().includes('/api/notifications') ? { items: [], unread_count: 0, pagination: { total: 0 } } : [])
    await route.fulfill({ status: result.status || 200, contentType: 'application/json',
      body: JSON.stringify({ code: result.status || 200, data }) })
  })
}
const question = (id) => ({ id, title: `问题${id}`, content: '说明', status: 'WAITING',
  course_name: '课程', video_title: '视频', student_name: '学生', video_time: 10 })
async function waitingFilter(page) {
  await page.locator('.filter-control .el-select').click()
  await page.getByRole('option', { name: '等待回答', exact: true }).click()
  await expect(page.locator('.filter-control')).toContainText('等待回答')
}

for (const action of ['answer', 'close']) {
  test(`答疑筛选最后一页${action}后移除失配项并回到有效页，慢请求禁止重复操作`, async ({ page }) => {
    let items = Array.from({ length: 9 }, (_, n) => question(n + 1))
    let writes = 0
    await isolate(page, 'TEACHER', async (url, request) => {
      if (url.pathname === '/api/questions') return { data: items.filter((item) => !url.searchParams.get('status') || item.status === url.searchParams.get('status')) }
      if (request.method() !== 'GET') {
        writes += 1
        await pause(800)
        const changed = { ...items[8], status: action === 'answer' ? 'ANSWERED' : 'CLOSED', answer: action === 'answer' ? { content: '正式回答' } : null }
        items[8] = changed
        return { data: changed }
      }
    })
    await page.goto('/teacher/questions')
    await waitingFilter(page)
    await page.locator('.el-pager li.number').filter({ hasText: /^2$/ }).click()
    await expect(page.locator('.teacher-question-card')).toHaveCount(1)
    if (action === 'answer') {
      await page.getByRole('button', { name: '回答问题', exact: true }).click()
      await page.getByPlaceholder('请输入清晰、准确的回答…').fill('正式回答')
      await page.getByRole('button', { name: '提交回答', exact: true }).click()
      await expect(page.getByRole('button', { name: '取消', exact: true })).toBeDisabled()
    } else {
      await page.getByRole('button', { name: '关闭', exact: true }).click()
      await page.getByRole('dialog', { name: '关闭问题' }).getByRole('button', { name: '确定', exact: true }).click()
      await expect(page.locator('.teacher-question-footer').getByRole('button', { name: '关闭', exact: true })).toBeDisabled()
    }
    await expect(page.locator('.teacher-question-card')).toHaveCount(8)
    await expect(page.locator('.teacher-question-card')).not.toContainText(['问题9'])
    expect(writes).toBe(1)
  })
}

test('作答期间学生关闭答疑，409后同步关闭状态而非继续提供保存入口', async ({ page }) => {
  const item = question(1)
  await isolate(page, 'TEACHER', (url, request) => {
    if (url.pathname === '/api/questions') return { data: [item] }
    if (url.pathname === '/api/questions/1/answer' && request.method() === 'POST') return { status: 409 }
    if (url.pathname === '/api/questions/1') return { data: { ...item, status: 'CLOSED' } }
  })
  await page.goto('/teacher/questions')
  await page.getByRole('button', { name: '回答问题', exact: true }).click()
  await page.getByPlaceholder('请输入清晰、准确的回答…').fill('草稿回答')
  await page.getByRole('button', { name: '提交回答', exact: true }).click()
  await expect(page.locator('.el-dialog:visible')).toHaveCount(0)
  await expect(page.locator('.teacher-question-card')).toContainText('已关闭')
  await expect(page.getByRole('button', { name: '回答问题', exact: true })).toHaveCount(0)
})

test('学习标签完整关联面板、方向键切换，取消收藏慢请求只写一次', async ({ page }) => {
  const items = Array.from({ length: 9 }, (_, n) => ({ id: n + 1, name: `课程${n + 1}`, learning_progress: 20 }))
  let writes = 0
  await isolate(page, 'STUDENT', async (url, request) => {
    if (url.pathname === '/api/learning/courses') return { data: items }
    if (url.pathname === '/api/learning/favorites') return { data: items }
    if (request.method() === 'DELETE') { writes += 1; await pause(800); return { data: {} } }
  })
  await page.goto('/learning')
  const enrolled = page.getByRole('tab', { name: /已加入/ })
  const favorites = page.getByRole('tab', { name: /我的收藏/ })
  await expect(page.locator('[role="tab"][tabindex="0"]')).toHaveCount(1)
  await enrolled.focus()
  await page.keyboard.press('ArrowRight')
  await expect(favorites).toBeFocused()
  await expect(favorites).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('tabpanel')).toHaveAttribute('id', 'learning-panel-favorites')
  await page.keyboard.press('Home')
  await expect(enrolled).toBeFocused()
  await page.keyboard.press('End')
  await expect(favorites).toBeFocused()
  await page.locator('.el-pager li.number:visible').filter({ hasText: /^2$/ }).click()
  const remove = page.getByRole('button', { name: '取消收藏', exact: true })
  await remove.click()
  await expect(page.getByRole('button', { name: '正在取消…', exact: true })).toBeDisabled()
  await expect(page.locator('.favorite-card')).toHaveCount(8)
  expect(writes).toBe(1)
})

for (const width of [1440, 390]) {
  for (const role of ['TEACHER', 'STUDENT']) {
    test(`答疑及消息连续长文本不溢出，保留正文换行-${role}-${width}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      const long = 'LongUnbrokenName'.repeat(30)
      const content = `${long}\n第二段正文`
      const errors = []
      page.on('pageerror', (error) => errors.push(error.message))
      await isolate(page, role, (url) => {
        if (url.pathname === '/api/questions') return { data: [{ ...question(1), title: long, content,
          course_name: long, video_title: long, student_name: long, answer: { content } }] }
        if (url.pathname === '/api/notifications') return { data: { items: [{ id: 1, title: long, content, sender_name: long,
          category: 'CLASS', read: false }], unread_count: 1, pagination: { page: 1, page_size: 12, total: 1 } } }
      })
      await page.goto(role === 'TEACHER' ? '/teacher/questions' : '/notifications')
      const copy = page.locator(role === 'TEACHER' ? '.question-content' : '.notification-copy p')
      await expect(copy).toContainText('第二段正文')
      await expect(copy).toHaveCSS('white-space', 'pre-wrap')
      const layout = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, width: document.documentElement.clientWidth }))
      expect(layout.scroll).toBeLessThanOrEqual(layout.width + 1)
      if (role === 'TEACHER') {
        await page.getByRole('button', { name: '编辑回答', exact: true }).click()
        await expect(page.getByRole('dialog', { name: '编辑回答' })).toBeVisible()
        await expect(page.locator('.answer-dialog-context')).toContainText('第二段正文')
      }
      expect(errors).toEqual([])
      await page.screenshot({ path: `../output/audit-20260913/修复后-长答疑消息-${role}-${width}.png`, fullPage: role !== 'TEACHER', animations: 'disabled' })
    })
  }
}
