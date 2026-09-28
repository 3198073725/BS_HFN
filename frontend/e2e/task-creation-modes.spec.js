import { expect, test } from '@playwright/test'


const teacher = { id: 8, role: 'TEACHER', username: 'mode_teacher', real_name: '模式测试教师' }
const course = { id: 3, name: '模式测试课程', status: 'PUBLISHED' }

async function isolateTeacher(page, handler) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'task-mode-token'))
  await page.route(/https?:\/\/[^/]+\/api\//, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const result = await handler(url, request) || {}
    const data = result.data ?? (url.pathname === '/api/users/me' ? teacher
      : url.pathname === '/api/notifications'
        ? { items: [], unread_count: 0, pagination: { total: 0 } }
        : [])
    await route.fulfill({
      status: result.status || 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: result.status || 200, message: 'OK', data }),
    })
  })
}

async function chooseCourse(dialog) {
  await dialog.locator('.el-select__wrapper').first().click()
  await dialog.page().getByRole('option', { name: /^模式测试课程/ }).click()
}

test('创建作业明确区分不限时与指定截止时间，不限时提交null', async ({ page }) => {
  let posted = null
  let homeworks = []
  await isolateTeacher(page, async (url, request) => {
    if (url.pathname === '/api/courses/mine') return { data: [course] }
    if (url.pathname === '/api/homeworks/manage') return { data: homeworks }
    if (url.pathname === '/api/homeworks' && request.method() === 'POST') {
      posted = request.postDataJSON()
      const saved = { id: 51, ...posted, course_name: course.name, status: 'DRAFT', submission_count: 0 }
      homeworks = [saved]
      return { status: 201, data: saved }
    }
  })

  await page.goto('/homeworks')
  await page.getByRole('button', { name: '＋ 创建作业' }).click()
  const dialog = page.getByRole('dialog', { name: '创建作业草稿' })
  await chooseCourse(dialog)
  await dialog.getByPlaceholder('例如：第一章知识总结').fill('不限时作业')
  await dialog.getByPlaceholder('说明完成要求、提交格式与评分要点…').fill('长期开放，教师手动关闭')
  await expect(dialog.getByRole('radio', { name: '不限时', exact: true })).toBeChecked()
  await expect(dialog.getByPlaceholder('请选择截止时间')).toHaveCount(0)
  await dialog.getByRole('button', { name: '保存草稿', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(posted.deadline).toBeNull()
  await expect(page.locator('.homework-card').filter({ hasText: '不限时作业' })).toContainText('长期有效')
})

test('在线试题只进入系统题库，附件试卷才显示文件上传', async ({ page }) => {
  let created = null
  let attachmentWrites = 0
  await isolateTeacher(page, async (url, request) => {
    if (url.pathname === '/api/courses/mine') return { data: [course] }
    if (url.pathname === '/api/exams/manage') return { data: created ? [created] : [] }
    if (url.pathname === '/api/exams' && request.method() === 'POST') {
      const payload = request.postDataJSON()
      created = {
        id: 61, ...payload, course_name: course.name, status: 'DRAFT', questions: [],
        submitted_count: 0, attachment: null, attachment_name: null,
      }
      return { status: 201, data: created }
    }
    if (url.pathname === '/api/exams/61') return { data: created }
    if (url.pathname.endsWith('/attachment') && request.method() !== 'GET') attachmentWrites += 1
  })

  await page.goto('/exams')
  await page.getByRole('button', { name: '＋ 创建测验' }).click()
  let dialog = page.getByRole('dialog', { name: '创建测验草稿' })
  await expect(dialog.getByRole('radio', { name: /在线试题/ })).toBeChecked()
  await expect(dialog).toContainText('保存基本信息后进入试题管理')
  await expect(dialog.locator('.teaching-attachment-field')).toHaveCount(0)
  await chooseCourse(dialog)
  await dialog.getByPlaceholder('例如：第一章基础测验').fill('真正的在线试题')
  await dialog.getByRole('button', { name: '保存并添加试题', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '真正的在线试题 · 试题管理' })).toBeVisible()
  expect(created.exam_type).toBe('ONLINE')
  expect(attachmentWrites).toBe(0)

  await page.getByRole('dialog', { name: '真正的在线试题 · 试题管理' })
    .getByRole('button', { name: '稍后继续', exact: true }).click()
  await page.getByRole('button', { name: '＋ 创建测验' }).click()
  dialog = page.getByRole('dialog', { name: '创建测验草稿' })
  await dialog.locator('label.el-radio').filter({ hasText: '附件试卷' }).click()
  await expect(dialog).toContainText('上传完整试卷文件')
  await expect(dialog.locator('.teaching-attachment-field')).toBeVisible()
  await expect(dialog).toContainText('完整试卷附件（必选）')
  await expect(dialog.getByRole('button', { name: '保存并发布', exact: true })).toBeVisible()
})
