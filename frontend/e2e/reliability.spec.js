import { expect, test } from '@playwright/test'
import { webcrypto } from 'node:crypto'
import { appendProgress, flushProgress, readProgressQueue } from '../src/utils/progressQueue.js'

globalThis.crypto ||= webcrypto
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// Mock only API endpoints; all Vue components and production styles are real.
async function isolate(page, handler) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'isolated-audit-token'))
  await page.route(/https?:\/\/[^/]+\/api\//, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const result = await handler(url, request)
    const data = result?.data ?? (url.pathname === '/api/users/me'
      ? { id: 1, role: 'STUDENT', real_name: '测试学生', created_at: new Date().toISOString() }
      : url.pathname === '/api/notifications'
        ? { items: [], unread_count: 0, pagination: { page: 1, page_size: 12, total: 0 } } : [])
    await route.fulfill(result?.raw ?? {
      status: result?.status || 200, contentType: 'application/json',
      body: JSON.stringify({ code: result?.status || 200, message: result?.message || 'OK', data }),
    })
  })
}

function onlineExam() {
  return {
    id: 1, title: '自动保存验证', course_name: '测试课程', exam_type: 'ONLINE', total_score: 100,
    status: 'PUBLISHED', availability: 'AVAILABLE', time_limit_minutes: 30, record: null,
    questions: [1, 2].map((id) => ({
      id, content: `题目${id}`, question_type: 'SINGLE', options: { A: '选项甲', B: '选项乙' }, score: 50,
    })),
  }
}

test('慢请求期间继续作答会补存最新答案，不提前显示保存成功', async ({ page }) => {
  const exam = onlineExam()
  const record = { id: 1, status: 'DOING', started_at: new Date().toISOString(), draft_answers: [] }
  const saves = []
  await isolate(page, async (url, request) => {
    if (url.pathname === '/api/exams') return { data: [exam] }
    if (url.pathname === '/api/exams/1') return { data: exam }
    if (url.pathname.endsWith('/start')) return { data: record }
    if (url.pathname.endsWith('/answers')) {
      saves.push(request.postDataJSON())
      await pause(1600)
      return { data: record }
    }
  })
  await page.goto('/exams')
  await page.getByRole('button', { name: '开始测验', exact: true }).click()
  await page.locator('.paper-question').nth(0).locator('label.el-radio').first().click()
  await expect.poll(() => saves.length).toBe(1)
  await page.locator('.paper-question').nth(1).locator('label.el-radio').first().click()
  await expect.poll(() => saves.length).toBe(2)
  expect(saves[1].answers.map((item) => item.question_id)).toEqual([1, 2])
  await expect(page.locator('.answer-save-state')).not.toHaveText('已自动保存')
  await expect(page.locator('.answer-save-state')).toHaveText('已自动保存')
})

test('老师关闭测验后保存冲突会同步学生交卷结果', async ({ page }) => {
  const exam = onlineExam()
  const record = { id: 1, status: 'DOING', started_at: new Date().toISOString(), draft_answers: [] }
  await isolate(page, async (url) => {
    if (url.pathname === '/api/exams') return { data: [exam] }
    if (url.pathname === '/api/exams/1') return { data: exam }
    if (url.pathname.endsWith('/start')) return { data: record }
    if (url.pathname.endsWith('/answers')) {
      exam.status = 'CLOSED'
      exam.record = { ...record, status: 'SUBMITTED', score: 0, total_score: 100, correct_count: 0, answers: [] }
      return { status: 409, message: '测验已关闭' }
    }
  })
  await page.goto('/exams')
  await page.getByRole('button', { name: '开始测验', exact: true }).click()
  await page.locator('.paper-question').first().locator('label.el-radio').first().click()
  await expect(page.locator('.result-score strong')).toHaveText('0')
  await expect(page.getByRole('button', { name: '提交测验', exact: true })).toHaveCount(0)
})

function homework(id) {
  return { id, title: `作业${id}`, description: '完成要求', course_name: '测试课程', status: 'PUBLISHED',
    total_score: 100, attachment: `homework/${id}/paper.txt`, submission: null }
}

test('作业附件失败后修改正文并重试会保存新正文和新附件', async ({ page }) => {
  const task = homework(1)
  let content = '', uploads = 0
  const puts = []
  await isolate(page, async (url, request) => {
    if (url.pathname === '/api/homeworks') return { data: [task] }
    if (url.pathname.endsWith('/submission')) {
      content = request.postDataJSON().content
      puts.push(content)
      return { data: { id: 1, status: 'SUBMITTED', content } }
    }
    if (url.pathname.endsWith('/submission/attachment')) {
      uploads += 1
      return { status: uploads === 1 ? 503 : 200, message: uploads === 1 ? '上传失败' : 'OK',
        data: { id: 1, status: 'SUBMITTED', content, attachment: 'answer.txt' } }
    }
  })
  await page.goto('/homeworks')
  await page.getByRole('button', { name: '提交作业', exact: true }).click()
  const dialog = page.locator('.el-dialog:visible')
  await expect(dialog.getByText(/教师批改后，内容和附件均不可再修改/)).toBeVisible()
  await dialog.getByPlaceholder('请输入作业答案或总结…').fill('旧答案')
  await dialog.locator('input[type=file]').setInputFiles({ name: 'answer.txt', mimeType: 'text/plain', buffer: Buffer.from('答案') })
  await dialog.getByRole('button', { name: '确认提交', exact: true }).click()
  await expect(page.getByText(/但附件上传失败/)).toBeVisible()
  await dialog.getByPlaceholder('请输入作业答案或总结…').fill('新答案')
  await dialog.getByRole('button', { name: '确认提交', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(puts).toEqual(['旧答案', '新答案'])
  expect(content).toBe('新答案')
  expect(uploads).toBe(2)
})

for (const firstStatus of [200, 503]) {
  test(`附件切换时忽略旧附件迟到的${firstStatus}响应`, async ({ page }) => {
    await isolate(page, async (url) => {
      if (url.pathname === '/api/homeworks') return { data: [homework(1), homework(2)] }
      if (url.pathname.endsWith('/attachment')) {
        const id = Number(url.pathname.split('/')[3])
        await pause(id === 1 ? 1600 : 100)
        return { raw: { status: id === 1 ? firstStatus : 200, contentType: 'text/plain', body: `附件${id}` } }
      }
    })
    await page.goto('/homeworks')
    const started = page.waitForRequest('**/api/homeworks/1/attachment')
    await page.locator('.homework-card').first().getByRole('button', { name: '在线预览教师附件' }).click()
    await started
    await page.locator('.el-dialog:visible').getByRole('button', { name: '关闭', exact: true }).click()
    await expect(page.locator('.el-dialog:visible')).toHaveCount(0)
    await page.locator('.homework-card').nth(1).getByRole('button', { name: '在线预览教师附件' }).click()
    const preview = page.locator('.el-dialog:visible iframe')
    await expect(preview).toBeVisible()
    await page.waitForTimeout(1900)
    await expect(page.locator('.el-dialog:visible .el-dialog__title')).toContainText('作业2')
    expect(await preview.evaluate(async (element) => (await fetch(element.src)).text())).toBe('附件2')
  })
}

test('快速切换教师主页时旧资料不会覆盖当前用户', async ({ page }) => {
  await isolate(page, async (url) => {
    if (/\/api\/users\/\d+$/.test(url.pathname)) {
      const id = Number(url.pathname.split('/').pop())
      await pause(id === 2 ? 1600 : 100)
      return { data: { id, real_name: `教师${id}`, role: 'TEACHER', created_at: new Date().toISOString(), courses: [] } }
    }
  })
  const started = page.waitForRequest('**/api/users/2')
  await page.goto('/users/2')
  await started
  await page.evaluate(() => { history.pushState({}, '', '/users/3'); window.dispatchEvent(new PopStateEvent('popstate')) })
  await expect(page.locator('.profile-identity h1')).toHaveText('教师3')
  await page.waitForTimeout(1800)
  await expect(page.locator('.profile-identity h1')).toHaveText('教师3')
})

test('消息中心未读开关正确渲染并触发筛选请求', async ({ page }) => {
  const warnings = []
  page.on('console', (message) => { if (message.type() === 'warning') warnings.push(message.text()) })
  await isolate(page, async (url) => {
    if (url.pathname === '/api/notifications') return { data: {
      items: [], unread_count: 0, pagination: { page: 1, page_size: 12, total: 0 },
    } }
  })
  await page.goto('/notifications')
  const switchControl = page.getByRole('switch')
  await expect(page.locator('.el-switch')).toBeVisible()
  const requested = page.waitForRequest((request) => {
    const url = new URL(request.url())
    return url.pathname === '/api/notifications' && url.searchParams.get('unread_only') === 'true'
  })
  await page.locator('.el-switch__core').click()
  await requested
  await expect(switchControl).toBeChecked()
  expect(warnings.filter((message) => message.includes('Failed to resolve component'))).toEqual([])
})

function memoryStorage() {
  const values = new Map()
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }
}

test('离线补传期间新增记录不丢失，重复触发只运行一次且按用户隔离', async () => {
  const storage = memoryStorage()
  const key = 'user:1'
  appendProgress(storage, key, { video_id: 1 })
  appendProgress(storage, 'user:2', { video_id: 99 })
  let release
  const waiting = new Promise((resolve) => { release = resolve })
  const sent = []
  const send = async (item) => { sent.push(item.video_id); if (item.video_id === 1) await waiting }
  const operation = flushProgress(storage, key, send, () => true)
  expect(flushProgress(storage, key, send, () => true)).toBe(operation)
  appendProgress(storage, key, { video_id: 2 })
  release()
  expect(await operation).toBe(2)
  expect(sent).toEqual([1, 2])
  expect(readProgressQueue(storage, key)).toEqual([])
  expect(readProgressQueue(storage, 'user:2').map((item) => item.video_id)).toEqual([99])
})

test('离线补传失败时保留原记录与期间新增记录，旧队列兼容并可恢复重试', async () => {
  const storage = memoryStorage()
  const key = 'legacy'
  storage.setItem(key, JSON.stringify([{ video_id: 1, queued_at: 1 }]))
  expect(readProgressQueue(storage, key)[0].queue_id).toBeTruthy()
  const operation = flushProgress(storage, key, async () => {
    appendProgress(storage, key, { video_id: 2 })
    throw new Error('断网')
  }, () => true)
  expect(await operation).toBe(0)
  expect(readProgressQueue(storage, key).map((item) => item.video_id)).toEqual([1, 2])
  expect(await flushProgress(storage, key, async () => {}, () => true)).toBe(2)
  expect(readProgressQueue(storage, key)).toEqual([])
})
