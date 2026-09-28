import { expect, test } from '@playwright/test'
import { appendProgress, flushProgress, readProgressQueue } from '../src/utils/progressQueue.js'

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const student = { id: 1, role: 'STUDENT', username: 'audit_student', real_name: '测试学生', created_at: new Date().toISOString() }

async function isolate(page, handler, user = student) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'isolated-audit-token'))
  await page.route(/https?:\/\/[^/]+\/api\//, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const result = await handler(url, request) || {}
    const data = result.data ?? (url.pathname === '/api/users/me' ? user
      : url.pathname === '/api/notifications' ? { items: [], unread_count: 0, pagination: { page: 1, page_size: 12, total: 0 } } : [])
    await route.fulfill({ status: result.status || 200, contentType: 'application/json',
      body: JSON.stringify({ code: result.status || 200, message: result.message || 'OK', data }) })
  })
}

function homework(id) {
  return { id, title: `作业${id}`, course_name: '测试课程', description: '完成要求', total_score: 100,
    status: 'PUBLISHED', submission: null, submission_count: id === 1 ? 1 : 0 }
}

function course() {
  return { id: 1, name: '上下文测试课程', status: 'PUBLISHED', teacher_id: 2, teacher_name: '教师',
    chapters: [{ id: 1, title: '第一章', videos: [1, 2].map((id) => ({ id, title: `视频${id}`, status: 'READY', duration: 60 })) }] }
}

test('课程中心支持分类、老师和关键词组合筛选及重置', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const items = [
    { id: 1, name: 'Python 数据分析', description: '使用 pandas 处理数据', category_id: 1, category_name: '编程开发', teacher_id: 11, teacher_name: '陈老师' },
    { id: 2, name: 'Java Web 开发', description: '接口设计', category_id: 1, category_name: '编程开发', teacher_id: 12, teacher_name: '王老师' },
    { id: 3, name: '操作系统基础', description: '进程与内存', category_id: 2, category_name: '计算机基础', teacher_id: 11, teacher_name: '陈老师' },
  ]
  const requests = []
  await isolate(page, async (url) => {
    if (url.pathname === '/api/courses/categories') return { data: [{ id: 1, name: '编程开发' }, { id: 2, name: '计算机基础' }] }
    if (url.pathname === '/api/courses/teachers') return { data: [
      { id: 11, name: '陈老师' }, { id: 12, name: '王老师' },
      ...Array.from({ length: 10 }, (_, index) => ({ id: 20 + index, name: `演示教师${index + 1}` })),
    ] }
    if (url.pathname === '/api/courses') {
      const params = Object.fromEntries(url.searchParams)
      requests.push(params)
      return { data: items.filter((item) => (!params.category_id || item.category_id === Number(params.category_id))
        && (!params.teacher_id || item.teacher_id === Number(params.teacher_id))
        && (!params.keyword || `${item.name} ${item.description}`.includes(params.keyword))) }
    }
  })
  await page.goto('/courses')
  await expect(page.locator('.course-card')).toHaveCount(3)
  const category = page.locator('.course-filter-field').filter({ hasText: '课程分类' })
  await category.locator('.el-select').click()
  await page.getByRole('option', { name: '编程开发', exact: true }).click()
  const teacher = page.locator('.course-filter-field').filter({ hasText: '授课老师' })
  await teacher.locator('.el-select').click()
  const teacherOptions = page.getByRole('listbox', { name: '授课老师' }).locator('..')
  await expect(teacherOptions).toHaveCSS('height', '216px')
  expect(await teacherOptions.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true)
  await page.getByRole('option', { name: '陈老师', exact: true }).click()
  await page.getByPlaceholder('搜索课程名称或简介').fill('Python')
  await page.getByPlaceholder('搜索课程名称或简介').press('Enter')
  await expect(page.locator('.course-card')).toHaveCount(1)
  await expect(page.locator('.course-card')).toContainText('Python 数据分析')
  await expect.poll(() => requests.at(-1)).toEqual({ category_id: '1', teacher_id: '11', keyword: 'Python' })
  await page.getByRole('button', { name: '重置', exact: true }).click()
  await expect(page.locator('.course-card')).toHaveCount(3)
  await expect(page.getByPlaceholder('搜索课程名称或简介')).toHaveValue('')
  const layout = await page.evaluate(() => ({
    fits: document.documentElement.scrollWidth <= innerWidth,
    viewport: innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    offenders: [...document.querySelectorAll('body *')]
      .filter((element) => element.getBoundingClientRect().right > innerWidth + 1)
      .slice(0, 8)
      .map((element) => ({ tag: element.tagName, className: String(element.className), right: element.getBoundingClientRect().right })),
  }))
  expect(layout.fits, JSON.stringify(layout)).toBe(true)
})

test('课程作业支持课程、状态和关键词组合筛选及重置', async ({ page }) => {
  const items = [
    { ...homework(1), course_id: 1, course_name: '课程甲', title: 'Java 阶段作业', deadline: '2027-09-13T04:00:00Z' },
    { ...homework(2), course_id: 2, course_name: '课程乙', title: 'Python 综合作业', status: 'CLOSED', availability: 'CLOSED' },
    { ...homework(3), course_id: 1, course_name: '课程甲', title: 'Java 补交作业', deadline: '2020-09-13T04:00:00Z', availability: 'ENDED' },
  ]
  await isolate(page, async (url) => url.pathname === '/api/homeworks' ? { data: items } : undefined)
  await page.goto('/homeworks')
  await expect(page.locator('.homework-card')).toHaveCount(3)
  await page.locator('.course-filter-field').filter({ hasText: '所属课程' }).locator('.el-select').click()
  await page.getByRole('option', { name: '课程甲', exact: true }).click()
  await expect(page.locator('.homework-card')).toHaveCount(2)
  await page.locator('.course-filter-field').filter({ hasText: '作业状态' }).locator('.el-select').click()
  await page.getByRole('option', { name: '进行中', exact: true }).click()
  await expect(page.locator('.homework-card')).toHaveCount(1)
  await page.getByRole('textbox', { name: '作业关键词' }).fill('阶段')
  await page.getByRole('textbox', { name: '作业关键词' }).press('Enter')
  await expect(page.locator('.course-result-meta')).toContainText('当前条件下共 1 项作业')
  await expect(page.locator('.homework-card')).toContainText('Java 阶段作业')
  await page.locator('.task-filter-panel').getByRole('button', { name: '重置', exact: true }).click()
  await expect(page.locator('.homework-card')).toHaveCount(3)
})

test('在线测验支持课程、方式、状态和关键词组合筛选及重置', async ({ page }) => {
  const base = {
    description: '筛选功能测试', questions: [], total_score: 100, time_limit_minutes: 30,
    status: 'PUBLISHED', start_time: null, end_time: '2027-09-13T04:00:00Z', record: null,
  }
  const items = [
    { ...base, id: 1, course_id: 1, course_name: '课程甲', title: 'Java 在线测验', exam_type: 'ONLINE', availability: 'AVAILABLE' },
    { ...base, id: 2, course_id: 1, course_name: '课程甲', title: 'Java 附件测验', exam_type: 'ATTACHMENT', availability: 'AVAILABLE' },
    { ...base, id: 3, course_id: 2, course_name: '课程乙', title: 'Python 已关闭测验', exam_type: 'ONLINE', status: 'CLOSED', availability: 'CLOSED' },
    { ...base, id: 4, course_id: 2, course_name: '课程乙', title: 'Python 预习测验', exam_type: 'ONLINE', start_time: '2027-08-13T04:00:00Z', availability: 'NOT_STARTED' },
  ]
  await isolate(page, async (url) => url.pathname === '/api/exams' ? { data: items } : undefined)
  await page.goto('/exams')
  await expect(page.locator('.exam-card')).toHaveCount(4)
  await page.locator('.course-filter-field').filter({ hasText: '所属课程' }).locator('.el-select').click()
  await page.getByRole('option', { name: '课程甲', exact: true }).click()
  await page.locator('.course-filter-field').filter({ hasText: '测验方式' }).locator('.el-select').click()
  await page.getByRole('option', { name: '附件试卷', exact: true }).click()
  await page.locator('.course-filter-field').filter({ hasText: '测验状态' }).locator('.el-select').click()
  await page.getByRole('option', { name: '进行中', exact: true }).click()
  await page.getByRole('textbox', { name: '测验关键词' }).fill('Java')
  await page.locator('.task-filter-panel').getByRole('button', { name: '查询', exact: true }).click()
  await expect(page.locator('.course-result-meta')).toContainText('当前条件下共 1 项测验')
  await expect(page.locator('.exam-card')).toContainText('Java 附件测验')
  await page.locator('.task-filter-panel').getByRole('button', { name: '重置', exact: true }).click()
  await expect(page.locator('.exam-card')).toHaveCount(4)
})

test('切换作业清空批改面板且批改请求中锁定操作', async ({ page }) => {
  let grades = 0
  const submission = { id: 11, homework_id: 1, student_name: '作业一学生', content: '作业一答案', status: 'SUBMITTED', submit_time: new Date().toISOString() }
  await isolate(page, async (url, request) => {
    if (url.pathname === '/api/homeworks/manage') return { data: [homework(1), homework(2)] }
    if (url.pathname === '/api/homeworks/1/submissions') return { data: [submission] }
    if (url.pathname.endsWith('/grade')) { grades += 1; await pause(1000); return { data: { ...submission, ...request.postDataJSON(), status: 'GRADED' } } }
  }, { ...student, role: 'TEACHER' })
  await page.goto('/homeworks')
  await page.getByRole('button', { name: '查看提交（1）' }).click()
  let dialog = page.locator('.el-dialog:visible')
  await dialog.getByRole('button', { name: '批改', exact: true }).click()
  await expect(page.locator('.grade-panel')).toContainText('作业一学生')
  await dialog.locator('.el-dialog__headerbtn').click()
  await expect(dialog).toBeHidden()
  await page.getByRole('button', { name: '查看提交（0）' }).click()
  await expect(page.locator('.grade-panel')).toHaveCount(0)
  await expect(page.locator('.el-dialog:visible')).not.toContainText('作业一答案')
  await page.locator('.el-dialog:visible .el-dialog__headerbtn').click()
  await expect(page.locator('.el-dialog:visible')).toHaveCount(0)
  await page.getByRole('button', { name: '查看提交（1）' }).click()
  dialog = page.locator('.el-dialog:visible')
  await dialog.getByRole('button', { name: '批改', exact: true }).click()
  await dialog.getByRole('button', { name: '保存批改' }).click()
  await expect(dialog.getByRole('button', { name: '批改', exact: true })).toBeDisabled()
  await expect(dialog.getByPlaceholder('填写教师评语（可选）')).toBeDisabled()
  await expect(dialog.locator('.el-dialog__headerbtn')).toHaveCount(0)
  await expect(page.locator('.grade-panel')).toHaveCount(0)
  expect(grades).toBe(1)
})

test('关闭提交列表后迟到响应不会污染另一份作业', async ({ page }) => {
  await isolate(page, async (url) => {
    if (url.pathname === '/api/homeworks/manage') return { data: [homework(1), homework(2)] }
    if (url.pathname === '/api/homeworks/1/submissions') {
      await pause(1600)
      return { data: [{ id: 11, homework_id: 1, student_name: '迟到的学生', content: '旧答案' }] }
    }
  }, { ...student, role: 'TEACHER' })
  await page.goto('/homeworks')
  const requested = page.waitForRequest('**/api/homeworks/1/submissions')
  await page.getByRole('button', { name: '查看提交（1）' }).click()
  await requested
  await page.locator('.el-dialog:visible .el-dialog__headerbtn').click()
  await expect(page.locator('.el-dialog:visible')).toHaveCount(0)
  await page.getByRole('button', { name: '查看提交（0）' }).click()
  await page.waitForTimeout(1800)
  await expect(page.locator('.el-dialog:visible')).not.toContainText('迟到的学生')
  await expect(page.locator('.el-dialog:visible .el-dialog__title')).toHaveText('作业2 · 提交记录')
})

test('作业提交中禁用正文和附件，失败后重新启用并保留内容', async ({ page }) => {
  const bodies = []
  await isolate(page, async (url, request) => {
    if (url.pathname === '/api/homeworks') return { data: [homework(1)] }
    if (url.pathname.endsWith('/submission')) {
      bodies.push(request.postDataJSON().content)
      await pause(1000)
      return bodies.length === 1 ? { status: 503, message: '临时保存失败' } : { data: { id: 1, status: 'SUBMITTED', content: bodies.at(-1) } }
    }
  })
  await page.goto('/homeworks')
  await page.getByRole('button', { name: '提交作业', exact: true }).click()
  const dialog = page.locator('.el-dialog:visible')
  const input = dialog.getByPlaceholder('请输入作业答案或总结…')
  await input.fill('完整答案')
  await dialog.getByRole('button', { name: '确认提交' }).click()
  await expect(input).toBeDisabled()
  await expect(dialog.locator('input[type=file]')).toBeDisabled()
  await expect(dialog.getByRole('button', { name: '取消', exact: true })).toBeDisabled()
  await expect(input).toBeEnabled()
  await expect(input).toHaveValue('完整答案')
  await dialog.getByRole('button', { name: '确认提交' }).click()
  await expect(dialog).toBeHidden()
  expect(bodies).toEqual(['完整答案', '完整答案'])
})

for (const type of ['笔记', '提问']) {
  test(`${type}保存期间切换视频不会串页`, async ({ page }) => {
    await isolate(page, async (url, request) => {
      if (url.pathname === '/api/courses/1') return { data: course() }
      if (url.pathname.endsWith('/state')) return { data: { joined: true, favorited: false } }
      if (url.pathname.endsWith('/progress')) return { data: { current_time: 0, progress: 0 } }
      if (request.method() === 'POST') {
        await pause(1400)
        return { data: { id: 1, video_id: 1, video_time: 0, content: '视频一内容', title: '视频一问题', status: 'WAITING' } }
      }
    })
    await page.goto('/courses/1')
    if (type === '笔记') {
      await page.getByPlaceholder('写下此处的重点、公式或思考…').fill('视频一内容')
      await page.getByRole('button', { name: '保存笔记' }).click()
    } else {
      await page.getByRole('button', { name: /我的提问/ }).click()
      await page.getByPlaceholder('用一句话概括问题').fill('视频一问题')
      await page.getByPlaceholder('说明你不理解的地方，便于教师准确回答…').fill('视频一内容')
      await page.getByRole('button', { name: '提交问题' }).click()
    }
    await page.locator('.video-list button').nth(1).click()
    await page.waitForTimeout(1700)
    await expect(page.locator('.video-list button.active')).toContainText('视频2')
    await expect(page.locator('.study-item')).toHaveCount(0)
  })
}

for (const action of ['保存资料', '上传头像', '移除头像']) {
  test(`${action}迟到响应不覆盖教师主页`, async ({ page }) => {
    const own = { ...student, avatar_url: '/audit-avatar.png' }
    await isolate(page, async (url, request) => {
      if (url.pathname === '/api/users/2') return { data: { id: 2, role: 'TEACHER', real_name: '当前教师', courses: [], created_at: new Date().toISOString() } }
      if (url.pathname.startsWith('/api/users/me') && request.method() !== 'GET') {
        await pause(1400)
        return { data: own }
      }
    }, own)
    await page.goto('/profile')
    const requested = page.waitForRequest((r) => new URL(r.url()).pathname.startsWith('/api/users/me') && r.method() !== 'GET')
    if (action === '保存资料') await page.getByRole('button', { name: '保存资料' }).click()
    else if (action === '上传头像') await page.locator('.profile-avatar-actions input[type=file]').setInputFiles({ name: 'avatar.png', mimeType: 'image/png', buffer: Buffer.from('isolated-image') })
    else {
      await page.getByRole('button', { name: '移除', exact: true }).click()
      await page.locator('.el-message-box').getByRole('button', { name: '确定', exact: true }).click()
    }
    await requested
    await page.evaluate(() => { history.pushState({}, '', '/users/2'); dispatchEvent(new PopStateEvent('popstate')) })
    await expect(page.locator('.profile-identity h1')).toHaveText('当前教师')
    await page.waitForTimeout(1600)
    await expect(page.locator('.profile-identity h1')).toHaveText('当前教师')
    await expect(page).toHaveURL('/users/2')
  })
}

for (const width of [1024, 390]) {
  test(`完整作业要求可阅读且弹窗固定、内部滚动 ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 600 })
    const description = Array.from({ length: 60 }, (_, i) => `第${i + 1}项要求：完成全部任务。`).join('\n')
    await isolate(page, async (url) => url.pathname === '/api/homeworks' ? { data: [{ ...homework(1), description }] } : undefined)
    await page.goto('/homeworks')
    await page.getByRole('button', { name: '查看完整要求' }).click()
    let dialog = page.locator('.el-dialog:visible')
    await expect(dialog.locator('.task-full-description')).toContainText('第60项要求')
    // Measure after the opening transition, not its temporary translateY(-20px).
    await expect.poll(async () => {
      const rect = await dialog.boundingBox()
      return Math.abs(rect.y + rect.height / 2 - 300)
    }).toBeLessThan(0.2)
    const box = await dialog.boundingBox()
    expect(Math.abs(box.x + box.width / 2 - width / 2)).toBeLessThan(1)
    expect(box.y).toBeGreaterThanOrEqual(15)
    expect(box.y + box.height).toBeLessThanOrEqual(585)
    await dialog.locator('.el-dialog__body').evaluate((e) => { e.scrollTop = e.scrollHeight })
    expect((await dialog.boundingBox()).y).toBeCloseTo(box.y, 1)
    await dialog.getByRole('button', { name: '关闭', exact: true }).click()
    await expect(dialog).toBeHidden()
    await page.getByRole('button', { name: '提交作业', exact: true }).click()
    dialog = page.locator('.el-dialog:visible')
    await dialog.locator('summary').click()
    await expect(dialog.locator('.task-full-description')).toContainText('第60项要求')
    await expect(dialog.getByRole('button', { name: '确认提交' })).toBeInViewport()
    await page.screenshot({ path: `test-results/full-homework-${width}.png` })
  })
}

test('截止状态只在卡片右上角显示且不再渲染重复底部状态', async ({ page }) => {
  await isolate(page, async (url) => url.pathname === '/api/homeworks'
    ? { data: [
        { ...homework(1), deadline: '2020-01-01T00:00:00Z' },
        homework(2),
        { ...homework(3), status: 'CLOSED', availability: 'CLOSED', can_submit: false },
      ] } : undefined)
  await page.goto('/homeworks')
  await expect(page.locator('.homework-summary article').nth(1).locator('strong')).toHaveText('1')
  const endedCard = page.locator('.homework-card').first()
  await expect(endedCard.locator('.homework-state')).toHaveText('已截止')
  await expect(endedCard.locator('.homework-actions')).toHaveCount(0)
  await expect(endedCard.locator('.homework-meta')).toContainText('截止 ·')
  const openCard = page.locator('.homework-card').nth(1)
  await expect(openCard.locator('.homework-actions')).toHaveCount(0)
  await expect(openCard.locator('.submission-result-summary').getByRole('button', { name: '提交作业', exact: true })).toBeVisible()
  const closedCard = page.locator('.homework-card').nth(2)
  await expect(closedCard.locator('.homework-state')).toHaveText('已关闭')
  await expect(closedCard.getByText('已关闭', { exact: true })).toHaveCount(1)
  await expect(closedCard.locator('.homework-actions')).toHaveCount(0)
  await expect(closedCard.locator('.homework-meta')).not.toContainText('已关闭')
})

test('分页作业中批改结果、长评语和完整要求入口始终位于卡片边框内', async ({ page }) => {
  const graded = {
    ...homework(1),
    deadline: '2027-09-13T02:08:54Z',
    attachment: 'homework/1/teacher/requirements.pdf',
    submission: {
      id: 1,
      status: 'GRADED',
      score: 100,
      teacher_comment: '整体完成得很好。'.repeat(80),
      attachment: 'homework/1/student/answer.pdf',
    },
  }
  const submitted = {
    ...homework(2),
    deadline: '2027-09-13T02:08:54Z',
    attachment: 'homework/2/teacher/requirements.pdf',
    submission: {
      id: 2,
      status: 'SUBMITTED',
      score: null,
      teacher_comment: null,
      attachment: 'homework/2/student/answer.pdf',
    },
  }
  const items = [graded, submitted, ...Array.from({ length: 5 }, (_, index) => ({
    ...homework(index + 3),
    deadline: '2027-09-13T02:08:54Z',
  }))]
  await isolate(page, async (url) => url.pathname === '/api/homeworks' ? { data: items } : undefined)
  await page.goto('/homeworks')
  const card = page.locator('.homework-card').first()
  await expect(card.locator('.submission-result-summary')).toContainText('已批改 · 不可修改')
  await expect(card.locator('.homework-actions')).toHaveCount(0)
  await expect(card.getByText('教师评语：', { exact: false })).toHaveCount(0)
  await card.getByRole('button', { name: '查看教师评语', exact: true }).click()
  const commentDialog = page.getByRole('dialog', { name: /教师评语/ })
  await expect(commentDialog).toContainText('整体完成得很好')
  await commentDialog.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(card.locator('.homework-meta')).toContainText('截止 ·')
  const editableCard = page.locator('.homework-card').nth(1)
  await expect(editableCard.locator('.homework-meta')).toContainText('截止 ·')
  const editButton = editableCard.locator('.submission-result-summary').getByRole('button', { name: '修改提交', exact: true })
  await expect(editButton).toBeEnabled()
  expect(await editButton.evaluate((element) => getComputedStyle(element).color)).toBe('rgb(40, 87, 127)')
  const layout = await editableCard.evaluate((element) => {
    const row = element.querySelector('.submission-result-summary')?.getBoundingClientRect()
    const button = element.querySelector('.submission-action-button')?.getBoundingClientRect()
    const teacherAttachment = element.querySelector('.homework-attachment')?.getBoundingClientRect()
    const studentAttachment = element.querySelector('.student-submission-attachment')?.getBoundingClientRect()
    return {
      rowTop: row?.top || 0,
      rowBottom: row?.bottom || 0,
      buttonTop: button?.top || 0,
      buttonBottom: button?.bottom || 0,
      teacherCenter: teacherAttachment ? teacherAttachment.top + teacherAttachment.height / 2 : 0,
      studentCenter: studentAttachment ? studentAttachment.top + studentAttachment.height / 2 : 0,
      teacherLeft: teacherAttachment?.left || 0,
      studentLeft: studentAttachment?.left || 0,
    }
  })
  expect(layout.buttonTop).toBeGreaterThanOrEqual(layout.rowTop - 1)
  expect(layout.buttonBottom).toBeLessThanOrEqual(layout.rowBottom + 1)
  expect(Math.abs(layout.teacherCenter - layout.studentCenter)).toBeLessThanOrEqual(1)
  expect(layout.studentLeft).toBeGreaterThan(layout.teacherLeft)
  const bounds = await card.evaluate((element) => {
    const cardRect = element.getBoundingClientRect()
    const resultRect = element.querySelector('.submission-result')?.getBoundingClientRect()
    const requirementRect = element.querySelector('.homework-requirement-button')?.getBoundingClientRect()
    return {
      cardBottom: cardRect.bottom,
      resultBottom: resultRect?.bottom || 0,
      requirementTop: requirementRect?.top || 0,
      requirementBottom: requirementRect?.bottom || 0,
    }
  })
  expect(bounds.resultBottom).toBeLessThanOrEqual(bounds.cardBottom + 1)
  expect(bounds.requirementTop).toBeGreaterThan(0)
  expect(bounds.requirementBottom).toBeLessThanOrEqual(bounds.cardBottom + 1)
  await expect(page.locator('.homework-grid')).toHaveCSS('overflow-y', 'visible')
  await editableCard.hover()
  const scrollBefore = await page.evaluate(() => scrollY)
  await page.mouse.wheel(0, 420)
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(scrollBefore)
})

test('停留在作业页面跨过截止时间后自动更新状态与提交入口', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-13T04:00:00Z') })
  await isolate(page, async (url) => url.pathname === '/api/homeworks'
    ? { data: [{ ...homework(1), deadline: '2026-09-13T04:00:10Z' }] } : undefined)
  await page.goto('/homeworks')
  await expect(page.getByRole('button', { name: '提交作业', exact: true })).toBeEnabled()
  await expect(page.locator('.homework-summary article').nth(1).locator('strong')).toHaveText('1')
  await page.clock.fastForward(11000)
  await expect(page.locator('.homework-state')).toHaveText('已截止')
  await expect(page.locator('.homework-actions')).toHaveCount(0)
  await expect(page.locator('.homework-summary article').nth(1).locator('strong')).toHaveText('0')
})

test('作业提交弹窗打开后跨过截止时间会立即锁定', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-13T04:00:00Z') })
  let submissions = 0
  await isolate(page, async (url, request) => {
    if (url.pathname === '/api/homeworks') {
      return { data: [{ ...homework(1), deadline: '2026-09-13T04:00:10Z' }] }
    }
    if (url.pathname.endsWith('/submission') && request.method() === 'PUT') submissions += 1
  })
  await page.goto('/homeworks')
  await expect(page.locator('.homework-meta')).toContainText('2026')
  await page.getByRole('button', { name: '提交作业', exact: true }).click()
  const dialog = page.locator('.el-dialog:visible')
  const answer = dialog.getByPlaceholder('请输入作业答案或总结…')
  await answer.fill('截止前正在填写')
  await page.clock.fastForward(11000)
  await expect(answer).toBeDisabled()
  await expect(dialog.getByRole('button', { name: '已截止', exact: true })).toBeDisabled()
  await expect(dialog).toContainText('不能继续提交')
  expect(submissions).toBe(0)
})

test('已截止作业的服务端状态会锁定列表和已打开的提交弹窗', async ({ page }) => {
  const item = { ...homework(1), deadline: null, availability: 'ENDED', is_expired: true, can_submit: false }
  await isolate(page, async (url) => url.pathname === '/api/homeworks' ? { data: [item] } : undefined)
  await page.goto('/homeworks')
  await expect(page.locator('.homework-state')).toHaveText('已截止')
  await expect(page.locator('.homework-actions')).toHaveCount(0)
})

test('测验跨过结束时间后自动显示已截止并禁止新开考', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-13T04:00:00Z') })
  const exam = {
    id: 1, title: '截止状态测验', course_name: '测试课程', description: '检查截止逻辑',
    questions: [], exam_type: 'ONLINE', status: 'PUBLISHED', availability: 'AVAILABLE',
    total_score: 100, time_limit_minutes: 30, start_time: null,
    end_time: '2026-09-13T04:00:10Z', record: null,
  }
  await isolate(page, async (url) => url.pathname === '/api/exams' ? { data: [exam] } : undefined)
  await page.goto('/exams')
  await expect(page.getByRole('button', { name: '开始测验', exact: true })).toBeEnabled()
  await page.clock.fastForward(11000)
  await expect(page.locator('.exam-state')).toHaveText('已截止')
  await expect(page.getByRole('button', { name: '开始测验', exact: true })).toBeDisabled()
  await expect(page.getByText('测验已经结束', { exact: true })).toBeVisible()
})

test('测验分页列表不截获滚轮并使用整个页面滚动', async ({ page }) => {
  const exams = Array.from({ length: 7 }, (_, index) => ({
    id: index + 1,
    title: `滚动测试测验${index + 1}`,
    course_name: '测试课程',
    description: '验证鼠标位于测验卡片上时仍然滚动整个页面。',
    questions: [],
    exam_type: 'ONLINE',
    status: 'PUBLISHED',
    availability: 'AVAILABLE',
    total_score: 100,
    time_limit_minutes: 30,
    start_time: null,
    end_time: '2027-09-13T04:00:00Z',
    record: null,
  }))
  await isolate(page, async (url) => url.pathname === '/api/exams' ? { data: exams } : undefined)
  await page.goto('/exams')
  const grid = page.locator('.exam-grid')
  await expect(grid).toHaveCSS('overflow-y', 'visible')
  await page.locator('.exam-card').first().hover()
  const scrollBefore = await page.evaluate(() => scrollY)
  await page.mouse.wheel(0, 420)
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(scrollBefore)
})

test('测验页面跨过开始时间后自动开放作答入口', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-13T04:00:00Z') })
  const exam = {
    id: 1, title: '即将开始的测验', course_name: '测试课程', description: '',
    questions: [], exam_type: 'ONLINE', status: 'PUBLISHED', availability: 'NOT_STARTED',
    total_score: 100, time_limit_minutes: 30, start_time: '2026-09-13T04:00:10Z',
    end_time: '2026-09-13T05:00:00Z', record: null,
  }
  await isolate(page, async (url) => url.pathname === '/api/exams' ? { data: [exam] } : undefined)
  await page.goto('/exams')
  await expect(page.locator('.exam-state')).toHaveText('未开始')
  await expect(page.getByRole('button', { name: '开始测验', exact: true })).toBeDisabled()
  await page.clock.fastForward(11000)
  await expect(page.locator('.exam-state')).toHaveText('已发布')
  await expect(page.getByRole('button', { name: '开始测验', exact: true })).toBeEnabled()
  await expect(page.getByText('可以作答', { exact: true })).toBeVisible()
})

test('教师端将已过结束时间但未手动关闭的任务标记为已截止', async ({ page }) => {
  const expiredHomework = { ...homework(1), availability: 'ENDED', is_expired: true, can_submit: false }
  const expiredExam = {
    id: 1, title: '已过期测验', course_name: '测试课程', description: '', questions: [],
    exam_type: 'ONLINE', total_score: 100, time_limit_minutes: 30, status: 'PUBLISHED',
    availability: 'ENDED', end_time: '2020-01-01T00:00:00Z', record_count: 0, submitted_count: 0,
  }
  await isolate(page, async (url) => {
    if (url.pathname === '/api/homeworks/manage') return { data: [expiredHomework] }
    if (url.pathname === '/api/exams/manage') return { data: [expiredExam] }
  }, { ...student, role: 'TEACHER' })
  await page.goto('/homeworks')
  await expect(page.locator('.homework-state')).toHaveText('已截止')
  await expect(page.locator('.homework-summary article').nth(1).locator('strong')).toHaveText('0')
  await expect(page.locator('.homework-summary article').nth(2).locator('strong')).toHaveText('1')
  await page.goto('/exams')
  await expect(page.locator('.exam-state')).toHaveText('已截止')
})

test('手机头像入口可用，课程详情按钮不拆行', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await isolate(page, async (url) => {
    if (url.pathname === '/api/courses/1') return { data: course() }
    if (url.pathname.endsWith('/state')) return { data: { joined: true, favorited: false } }
    if (url.pathname.endsWith('/progress')) return { data: { current_time: 0, progress: 0 } }
  })
  await page.goto('/courses/1')
  await expect(page.getByRole('link', { name: '查看并编辑个人主页' })).toBeVisible()
  const heights = await page.locator('.hero-small-button').evaluateAll((es) => es.map((e) => ({ h: e.getBoundingClientRect().height, wrap: getComputedStyle(e).whiteSpace })))
  expect(heights.length).toBeGreaterThanOrEqual(2)
  expect(heights.every((item) => item.wrap === 'nowrap' && item.h <= 42)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('link', { name: '查看并编辑个人主页' }).click()
  await expect(page).toHaveURL('/profile')
})

test('通知双击仅标记一次，未读筛选移除已读项并同步数量', async ({ page }) => {
  let puts = 0
  const items = [1, 2].map((id) => ({ id, title: `通知${id}`, content: '内容', category: 'SYSTEM', read: false, sender_name: '系统', created_at: new Date().toISOString() }))
  await isolate(page, async (url) => {
    if (url.pathname === '/api/notifications') {
      const filtered = url.searchParams.get('unread_only') === 'true' ? items.filter((i) => !i.read) : items
      return { data: { items: filtered, unread_count: items.filter((i) => !i.read).length, pagination: { page: 1, page_size: 12, total: filtered.length } } }
    }
    if (url.pathname.endsWith('/read')) { puts += 1; await pause(1000); items[0].read = true; return { data: items[0] } }
  })
  await page.goto('/notifications')
  await page.locator('.el-switch__core').click()
  await expect(page.locator('.notification-item')).toHaveCount(2)
  // Dispatch two click events even if the first disables the button.
  await page.locator('.notification-item').first().evaluate((e) => {
    e.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    e.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
  await expect(page.locator('.notification-toolbar strong')).toHaveText('1')
  await expect(page.locator('.notification-item')).toHaveCount(1)
  await expect(page.locator('.notification-item')).toContainText('通知2')
  expect(puts).toBe(1)
})

for (const [path, endpoint, title, role] of [
  ['/courses', '/api/courses', '课程列表加载失败', 'STUDENT'],
  ['/learning', '/api/learning/courses', '学习中心加载失败', 'STUDENT'],
  ['/homeworks', '/api/homeworks', '作业列表加载失败', 'STUDENT'],
  ['/exams', '/api/exams', '测验列表加载失败', 'STUDENT'],
  ['/notifications', '/api/notifications', '通知加载失败', 'STUDENT'],
  ['/statistics', '/api/statistics', '统计数据加载失败', 'STUDENT'],
  ['/classes', '/api/classes', '班级信息加载失败', 'STUDENT'],
  ['/teacher/courses', '/api/courses/mine', '教学课程加载失败', 'TEACHER'],
  ['/teacher/questions', '/api/questions', '答疑列表加载失败', 'TEACHER'],
]) {
  test(`${path}加载失败显示错误与重试，不伪装为空数据`, async ({ page }) => {
    let failing = true
    await isolate(page, async (url) => url.pathname === endpoint && failing ? { status: 503, message: '服务暂时不可用' } : undefined,
      { ...student, role })
    await page.goto(path)
    await expect(page.locator('.el-result__title')).toHaveText(title)
    await expect(page.locator('.el-empty')).toHaveCount(0)
    failing = false
    await page.getByRole('button', { name: '重新加载', exact: true }).click()
    await expect(page.locator('.el-result')).toHaveCount(0)
  })
}

test('补传临时错误保留实时队列，恢复后可重试；明确永久错误才删除', async () => {
  for (const status of [500, 502, 503, 504, 429, 401, 409, undefined]) {
    const values = new Map()
    const storage = { getItem: (key) => values.get(key), setItem: (key, value) => values.set(key, value) }
    await appendProgress(storage, 'user:1', { video_id: 1 })
    await flushProgress(storage, 'user:1', async () => { await appendProgress(storage, 'user:1', { video_id: 2 }); throw { code: status } }, () => false)
    expect(readProgressQueue(storage, 'user:1').map((i) => i.video_id)).toEqual([1, 2])
    expect(await flushProgress(storage, 'user:1', async () => {}, () => false)).toBe(2)
    await appendProgress(storage, 'user:1', { video_id: 3 })
    await flushProgress(storage, 'user:1', async () => { throw { code: 404 } }, () => false)
    expect(readProgressQueue(storage, 'user:1')).toEqual([])
  }
})

test('服务器暂时失败后在课程页自动延迟补传，无需刷新页面', async ({ page }) => {
  let puts = 0
  await page.addInitScript(() => localStorage.setItem('bs-hfn:progress-queue:1', JSON.stringify([
    { queue_id: 'retry-entry', video_id: 1, current_time: 15, watch_duration_delta: 10 },
  ])))
  await isolate(page, async (url, request) => {
    if (url.pathname === '/api/courses/1') return { data: course() }
    if (url.pathname.endsWith('/state')) return { data: { joined: true, favorited: false } }
    if (url.pathname.endsWith('/progress')) {
      if (request.method() === 'GET') return { data: { current_time: 0, progress: 0 } }
      puts += 1
      return puts === 1 ? { status: 503, message: '服务暂时不可用' } : { data: { current_time: 15, progress: 25 } }
    }
  })
  await page.goto('/courses/1')
  await expect.poll(() => puts).toBe(2)
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('bs-hfn:progress-queue:1')).length)).toBe(0)
})

for (const existingAttachment of [true, false]) {
  test(`清空旧正文改为附件提交；已有附件=${existingAttachment}`, async ({ page }) => {
    const submission = { id: 1, homework_id: 1, status: 'SUBMITTED', content: '待删除的旧正文', attachment: existingAttachment ? 'old.txt' : null }
    let uploads = 0
    const puts = []
    await isolate(page, async (url, request) => {
      if (url.pathname === '/api/homeworks') return { data: [{ ...homework(1), submission }] }
      if (url.pathname.endsWith('/submission/attachment')) {
        uploads += 1
        if (uploads === 1) return { status: 503, message: '临时上传失败' }
        submission.attachment = 'new.txt'
        return { data: submission }
      }
      if (url.pathname.endsWith('/submission')) {
        puts.push(request.postDataJSON().content)
        submission.content = request.postDataJSON().content
        return { data: submission }
      }
    })
    await page.goto('/homeworks')
    await page.getByRole('button', { name: '修改提交', exact: true }).click()
    const dialog = page.locator('.el-dialog:visible')
    await dialog.getByPlaceholder('请输入作业答案或总结…').fill('')
    if (!existingAttachment) await dialog.locator('input[type=file]').setInputFiles({ name: 'new.txt', mimeType: 'text/plain', buffer: Buffer.from('answer') })
    await dialog.getByRole('button', { name: '确认提交' }).click()
    if (!existingAttachment) {
      await expect(page.getByText(/但附件上传失败/)).toBeVisible()
      expect(submission.content).toBe('待删除的旧正文')
      expect(puts).toEqual([])
      await dialog.getByRole('button', { name: '确认提交' }).click()
    }
    await expect(dialog).toBeHidden()
    expect(puts).toEqual([''])
    expect(submission.content).toBe('')
    expect(submission.attachment).toBe(existingAttachment ? 'old.txt' : 'new.txt')
  })
}

for (const width of [1440, 390]) {
  test(`公告支持全文、全部列表与分页 ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 700 })
    const items = Array.from({ length: 9 }, (_, i) => ({ id: i + 1, title: `公告${i + 1}`,
      content: Array.from({ length: 80 }, (_, n) => `第${n + 1}行完整公告内容。`).join('\n'), publish_time: new Date().toISOString() }))
    await isolate(page, async (url) => url.pathname === '/api/notices' ? { data: items } : undefined)
    await page.goto('/')
    await expect(page.getByText('正常运行', { exact: true })).toHaveCount(0)
    await page.getByRole('link', { name: '阅读全文', exact: true }).first().click()
    let dialog = page.locator('.el-dialog:visible')
    await expect(dialog.locator('.task-full-description')).toContainText('第80行完整公告内容')
    await expect.poll(async () => { const r = await dialog.boundingBox(); return Math.abs(r.y + r.height / 2 - 350) }).toBeLessThan(0.2)
    await expect(dialog.getByRole('button', { name: '关闭', exact: true })).toBeInViewport()
    await dialog.getByRole('button', { name: '关闭', exact: true }).click()
    await expect(dialog).toBeHidden()
    await expect(page.locator('.public-notice-list article')).toHaveCount(8)
    const pager = page.locator('.public-notice-list .el-pagination')
    const firstPageY = await pager.evaluate((element) => element.getBoundingClientRect().top + window.scrollY)
    await pager.locator('.btn-next').click()
    await expect(page.locator('.public-notice-list article')).toHaveCount(1)
    await expect(page.locator('.public-notice-list h2')).toHaveText('公告9')
    const lastPageY = await pager.evaluate((element) => element.getBoundingClientRect().top + window.scrollY)
    expect(Math.abs(lastPageY - firstPageY)).toBeLessThan(1)
    await page.getByRole('button', { name: '阅读全文', exact: true }).click()
    dialog = page.locator('.el-dialog:visible')
    await expect(dialog.locator('.el-dialog__title')).toHaveText('公告9')
    await expect.poll(async () => { const r = await dialog.boundingBox(); return Math.abs(r.y + r.height / 2 - 350) }).toBeLessThan(0.2)
    await page.screenshot({ path: `test-results/notice-detail-${width}.png` })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

test('提交详情加载失败支持重试，不展示没有学生提交', async ({ page }) => {
  let failing = true
  await isolate(page, async (url) => {
    if (url.pathname === '/api/homeworks/manage') return { data: [homework(1)] }
    if (url.pathname === '/api/homeworks/1/submissions' && failing) return { status: 503, message: '提交列表暂时不可用' }
  }, { ...student, role: 'TEACHER' })
  await page.goto('/homeworks')
  await page.getByRole('button', { name: '查看提交（1）' }).click()
  const dialog = page.locator('.el-dialog:visible')
  await expect(dialog.locator('.el-result__title')).toHaveText('提交记录加载失败')
  await expect(dialog.locator('.el-empty')).toHaveCount(0)
  failing = false
  await dialog.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(dialog.locator('.el-result')).toHaveCount(0)
  await expect(dialog.locator('.el-empty')).toHaveCount(1)
})

test('测验完整说明在详情与作答弹窗均可阅读', async ({ page }) => {
  const description = '第一行\n第二行\n第三行\n第四行\n第五行重要测验要求'
  const exam = { id: 1, title: '测验说明', course_name: '课程', description, questions: [], exam_type: 'ATTACHMENT',
    status: 'PUBLISHED', availability: 'AVAILABLE', total_score: 100, record: null }
  await isolate(page, async (url) => {
    if (url.pathname === '/api/exams') return { data: [exam] }
    if (url.pathname === '/api/exams/1') return { data: exam }
    if (url.pathname.endsWith('/start')) return { data: { id: 1, status: 'DOING', started_at: new Date().toISOString() } }
  })
  await page.goto('/exams')
  await page.getByRole('button', { name: '查看完整说明' }).click()
  await expect(page.locator('.el-dialog:visible .task-full-description')).toContainText('第五行重要测验要求')
  await page.locator('.el-dialog:visible').getByRole('button', { name: '关闭', exact: true }).click()
  await expect(page.locator('.el-dialog:visible')).toHaveCount(0)
  await page.getByRole('button', { name: '开始测验', exact: true }).click()
  await page.locator('.el-dialog:visible summary').click()
  await expect(page.locator('.el-dialog:visible .task-full-description')).toContainText('第五行重要测验要求')
})
