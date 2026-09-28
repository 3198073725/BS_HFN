import { expect, test } from '@playwright/test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expectCompactMessageBox } from './message-box-layout'


const password = 'E2ePassword123!'
const testDirectory = dirname(fileURLToPath(import.meta.url))
const uploadFixture = resolve(
  testDirectory,
  '../../backend/.e2e-media/videos/original/e2e-upload.mp4',
)


async function login(page, account) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名、邮箱、学号或工号').fill(account)
  await page.getByPlaceholder('请输入登录密码').fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('button', { name: '退出' })).toBeVisible()
}


async function expectNoHorizontalOverflow(page) {
  const widths = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }))
  expect(widths.scroll).toBeLessThanOrEqual(widths.client)
}

async function expectFixedDialog(page, roleDialog) {
  const window = roleDialog.locator('.el-dialog')
  await expect(window).toBeVisible()
  const viewport = page.viewportSize()
  await expect.poll(async () => {
    const box = await window.boundingBox()
    return Math.max(Math.abs(box.x + box.width / 2 - viewport.width / 2),
      Math.abs(box.y + box.height / 2 - viewport.height / 2))
  }).toBeLessThanOrEqual(0.2)
  const before = await window.boundingBox()
  expect(before.y).toBeGreaterThanOrEqual(15)
  expect(before.y + before.height).toBeLessThanOrEqual(viewport.height - 15)
  await window.locator(':scope > .el-dialog__body').evaluate((element) => { element.scrollTop += 250 })
  const after = await window.boundingBox()
  expect(Math.abs(before.y - after.y)).toBeLessThanOrEqual(0.2)
  expect(await window.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
}


async function expectStandardControlSizes(page) {
  const selector = [
    '.el-button:not(.is-circle)',
    '.action-link',
    '.portal-button',
    '.header-action',
    '.hero-small-button',
    '.study-tabs > button',
    '.learning-card-actions > a',
    '.learning-card-actions > button',
    '.time-anchor',
  ].join(', ')
  const undersized = await page.locator(selector).evaluateAll((elements) => elements
    .filter((element) => {
      const style = getComputedStyle(element)
      return style.display !== 'none' && style.visibility !== 'hidden' && element.getBoundingClientRect().width > 0
    })
    .map((element) => ({
      label: element.textContent?.trim().slice(0, 30),
      height: element.getBoundingClientRect().height,
    }))
    .filter((control) => control.height < 31.5))
  expect(undersized).toEqual([])
}


test('登录表单提示完整，受保护页面登录后回到原路径', async ({ page }) => {
  await page.goto('/learning')
  await expect(page).toHaveURL(/\/login\?redirect=\/learning$/)
  await expect(page.getByPlaceholder('用户名、邮箱、学号或工号')).toBeVisible()
  await expect(page.getByPlaceholder('请输入登录密码')).toBeVisible()

  await page.getByPlaceholder('用户名、邮箱、学号或工号').fill('e2e_student')
  await page.getByPlaceholder('请输入登录密码').fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL('/learning')
  await expect(page.getByRole('heading', { name: '我的学习' })).toBeVisible()
})


test('忘记密码可完成身份核验和密码重置请求', async ({ page }) => {
  let submittedPayload = null
  await page.route('**/api/auth/reset-password', async (route) => {
    submittedPayload = route.request().postDataJSON()
    await route.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 202,
        message: '申请已提交，请等待班级教师同意后使用新密码登录',
        data: { status: 'PENDING' },
      }),
    })
  })
  await page.goto('/login')
  await page.getByRole('button', { name: '忘记密码', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '找回密码' })
  await dialog.getByPlaceholder('请输入用户名').fill('e2e_student')
  await dialog.getByPlaceholder('注册邮箱、学号、工号或手机号').fill('E2ES001')
  await dialog.getByPlaceholder('8–72 位新密码').fill('NewPassword123!')
  await dialog.getByPlaceholder('再次输入新密码').fill('NewPassword123!')
  await dialog.getByRole('button', { name: '提交重置', exact: true }).click()

  await expect(page.getByText('申请已提交，请等待班级教师同意后使用新密码登录')).toBeVisible()
  await expect(dialog).toBeHidden()
  expect(submittedPayload).toEqual({
    username: 'e2e_student',
    verification: 'E2ES001',
    new_password: 'NewPassword123!',
  })
})


test('学生可以查看站内通知并全部标为已读', async ({ page }) => {
  await login(page, 'e2e_student')
  await page.locator('a[href="/notifications"]').click()
  await expect(page).toHaveURL('/notifications')
  await expect(page.getByRole('heading', { name: '消息中心', exact: true })).toBeVisible()
  await expect(page.getByText('端到端消息中心验证', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '全部标为已读', exact: true }).click()
  await expect(page.getByText('全部通知已标记为已读')).toBeVisible()
  await expect(page.getByText('0', { exact: true }).first()).toBeVisible()
})


test('刷新令牌失效后清除本地会话并返回登录页', async ({ page }) => {
  await login(page, 'e2e_student')
  await page.route('**/api/learning/courses', (route) => route.fulfill({
    status: 401,
    contentType: 'application/json',
    body: JSON.stringify({ code: 401, message: 'Token 已过期', data: null }),
  }))
  await page.route('**/api/auth/refresh', (route) => route.fulfill({
    status: 401,
    contentType: 'application/json',
    body: JSON.stringify({ code: 401, message: 'Token 已失效', data: null }),
  }))

  await page.getByRole('link', { name: '我的学习', exact: true }).click()
  await expect(page).toHaveURL(/\/login\?redirect=\/learning$/)
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
  const storedTokens = await page.evaluate(() => ({
    access: localStorage.getItem('access_token'),
    refresh: localStorage.getItem('refresh_token'),
  }))
  expect(storedTokens).toEqual({ access: null, refresh: null })
})


test('访问令牌损坏时使用刷新令牌恢复请求', async ({ page }) => {
  await login(page, 'e2e_student')
  await page.evaluate(() => localStorage.setItem('access_token', 'invalid-token'))

  await page.getByRole('link', { name: '我的学习', exact: true }).click()
  await expect(page).toHaveURL('/learning')
  await expect(page.getByRole('heading', { name: '我的学习', exact: true })).toBeVisible()
  // The heading renders before requests finish; wait for the actual refreshed session.
  await expect.poll(() => page.evaluate(() => {
    const token = localStorage.getItem('access_token')
    return Boolean(token && token !== 'invalid-token')
  })).toBe(true)
  await expect(page.locator('.learning-course-card').first()).toBeVisible()
})


test('公开课程在本地会话完全失效后自动降级为匿名访问', async ({ page }) => {
  await login(page, 'e2e_student')
  await page.evaluate(() => {
    localStorage.setItem('access_token', 'invalid-access-token')
    localStorage.setItem('refresh_token', 'invalid-refresh-token')
  })

  await page.goto('/courses/1')
  await expect(page.getByRole('heading', { name: '端测基础课程', exact: true })).toBeVisible()
  await expect(page.getByText('课程加载失败')).toBeHidden()
  await expect(page.getByText('Not enough segments')).toBeHidden()
  const storedTokens = await page.evaluate(() => ({
    access: localStorage.getItem('access_token'),
    refresh: localStorage.getItem('refresh_token'),
  }))
  expect(storedTokens).toEqual({ access: null, refresh: null })
})


test('学生从课程详情申请入班并由教师审批', async ({ page }) => {
  await login(page, 'e2e_student')
  await page.goto('/courses/1')

  const teacherLink = page.locator('.teacher-profile-link')
  await expect(teacherLink).toContainText('端测教师')
  await teacherLink.click()
  await expect(page).toHaveURL(/\/users\/\d+$/)
  await expect(page.getByRole('heading', { name: '端测教师', exact: true })).toBeVisible()
  await expect(page.getByText('已发布课程', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: /端测基础课程/ })).toBeVisible()

  await page.goto('/courses/1')
  const classEntry = page.getByRole('button', { name: '查看课程班级', exact: true })
  await expect(classEntry).toHaveText('已加入班级')
  await classEntry.click()
  const dialog = page.getByRole('dialog', { name: '选择课程班级' })
  await expect(dialog.getByText('端测密码审批班', { exact: true })).toBeVisible()
  const availableClass = dialog.locator('.course-class-option').filter({ hasText: '端测自主加入班' })
  await availableClass.getByRole('button', { name: '申请加入', exact: true }).click()
  await expect(page.getByText('已申请加入“端测自主加入班”，请等待教师审批')).toBeVisible()
  await expect(availableClass.getByRole('button', { name: '待教师审批', exact: true })).toBeDisabled()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()

  await page.getByRole('link', { name: '我的班级', exact: true }).click()
  const joinHistory = page.locator('[aria-label="我的入班申请"]')
  await expect(joinHistory).toContainText('端测自主加入班')
  await expect(joinHistory).toContainText('待教师审批')
  await joinHistory.getByRole('button', { name: '撤回申请', exact: true }).click()
  await page.getByRole('dialog', { name: '撤回入班申请' })
    .getByRole('button', { name: '确认撤回', exact: true }).click()
  await expect(page.getByText('入班申请已撤回')).toBeVisible()
  await expect(joinHistory).toContainText('已撤回')

  await page.goto('/courses/1')
  await expect(classEntry).toHaveText('已加入班级')
  await classEntry.click()
  const reopenedDialog = page.getByRole('dialog', { name: '选择课程班级' })
  const cancelledClass = reopenedDialog.locator('.course-class-option').filter({ hasText: '端测自主加入班' })
  await cancelledClass.getByRole('button', { name: '再次申请', exact: true }).click()
  await expect(cancelledClass.getByRole('button', { name: '待教师审批', exact: true })).toBeDisabled()
  await page.keyboard.press('Escape')

  await page.getByRole('button', { name: '退出', exact: true }).click()
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '班级管理', exact: true }).click()
  const classroomCard = page.locator('.classroom-card').filter({ hasText: '端测自主加入班' })
  const requestPanel = classroomCard.locator('.classroom-join-panel')
  await expect(requestPanel).toContainText('端测学生')
  await requestPanel.getByRole('button', { name: '同意入班', exact: true }).click()
  await page.getByRole('dialog', { name: '同意入班申请' })
    .getByRole('button', { name: '确认同意', exact: true }).click()
  await expect(page.getByText('已同意入班申请，学生已加入班级')).toBeVisible()
  await expect(classroomCard.locator('.el-table')).toContainText('端测学生')

  await page.getByRole('button', { name: '退出', exact: true }).click()
  await login(page, 'e2e_student')
  await page.getByRole('link', { name: '我的班级', exact: true }).click()
  await expect(page.locator('.classroom-card').filter({ hasText: '端测自主加入班' })).toBeVisible()
  await expect(page.locator('[aria-label="我的入班申请"]')).toContainText('已通过')
  await page.goto('/courses/1')
  await expect(classEntry).toHaveText('已加入班级')
  await classEntry.click()
  await expect(page.getByRole('dialog', { name: '选择课程班级' })
    .locator('.course-class-option').filter({ hasText: '端测自主加入班' })
    .getByRole('button', { name: '已加入', exact: true })).toBeDisabled()
  await page.keyboard.press('Escape')
  await page.locator('a[href="/notifications"]').click()
  await expect(page.getByText('班级通知', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('CLASS', { exact: true })).toHaveCount(0)
})

test('课程班级入口同步未加入、待审批和已加入状态', async ({ page }) => {
  await login(page, 'e2e_student')
  let joined = false
  let requestStatus = null
  await page.route('**/api/learning/courses/1/state', async (route) => {
    await route.fulfill({ json: { data: { joined, favorited: false } } })
  })
  await page.route('**/api/courses/1/classes', async (route) => {
    await route.fulfill({ json: { data: [{
      id: 999, name: '状态同步测试班', description: '', member_count: joined ? 1 : 0,
      joined, request_status: requestStatus,
    }] } })
  })
  await page.route('**/api/courses/1/classes/999/apply', async (route) => {
    requestStatus = 'PENDING'
    await route.fulfill({ status: 202, json: { data: { status: 'PENDING' } } })
  })
  await page.goto('/courses/1')
  const classEntry = page.getByRole('button', { name: '查看课程班级', exact: true })
  await expect(classEntry).toHaveText('加入班级')
  await expect(page.getByRole('button', { name: '＋ 加入课程', exact: true })).toBeEnabled()
  await classEntry.click()
  await page.getByRole('dialog', { name: '选择课程班级' })
    .getByRole('button', { name: '申请加入', exact: true }).click()
  await expect(classEntry).toHaveText('待教师审批')
  await page.keyboard.press('Escape')
  await page.reload()
  await expect(classEntry).toHaveText('待教师审批')

  joined = true
  requestStatus = 'APPROVED'
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(classEntry).toHaveText('已加入班级')
  await expect(page.getByRole('button', { name: '✓ 已加入课程', exact: true })).toBeDisabled()
  await classEntry.click()
  await expect(page.getByRole('dialog', { name: '选择课程班级' })
    .getByRole('button', { name: '已加入', exact: true })).toBeDisabled()
  await page.keyboard.press('Escape')

  joined = false
  for (const status of ['REJECTED', 'CANCELLED']) {
    requestStatus = status
    await page.reload()
    await expect(classEntry).toHaveText('加入班级')
  }
})


test('右上角头像进入个人主页并可编辑资料', async ({ page }) => {
  await login(page, 'e2e_student')
  const profileEntry = page.locator('.user-chip')
  await expect(profileEntry).toHaveAttribute('href', '/profile')
  await profileEntry.click()
  await expect(page).toHaveURL('/profile')
  await expect(page.getByRole('heading', { name: '编辑我的主页', exact: true })).toBeVisible()
  await page.getByPlaceholder('介绍你的教学方向、学习兴趣或个人经历').fill('喜欢通过课程练习巩固知识。')
  await page.getByRole('button', { name: '保存资料', exact: true }).click()
  await expect(page.getByText('个人资料已保存')).toBeVisible()
  await expect(page.getByPlaceholder('介绍你的教学方向、学习兴趣或个人经历')).toHaveValue('喜欢通过课程练习巩固知识。')
})


test('其他标签页退出后当前受保护页面同步返回登录页', async ({ page, context }) => {
  await login(page, 'e2e_student')
  await page.getByRole('link', { name: '我的学习', exact: true }).click()
  await expect(page).toHaveURL('/learning')

  const otherPage = await context.newPage()
  await otherPage.goto('/')
  await otherPage.evaluate(() => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  })

  await expect(page).toHaveURL(/\/login\?redirect=\/learning$/)
  await expect(page.getByRole('heading', { name: '欢迎回来' })).toBeVisible()
  await otherPage.close()
})


test('学生可以访问学习、班级、作业、测验和数据页面', async ({ page }) => {
  await login(page, 'e2e_student')
  for (const item of [
    ['我的学习', '我的学习'],
    ['我的班级', '我的班级'],
    ['课程作业', '课程作业'],
    ['在线测验', '在线测验'],
    ['数据概览', '学习数据'],
  ]) {
    await page.getByRole('link', { name: item[0], exact: true }).click()
    await expect(page.getByRole('heading', { name: item[1], exact: true })).toBeVisible()
    await expectStandardControlSizes(page)
  }
})


test('教师可以访问班级、教学、作业、测验、答疑和数据页面', async ({ page }) => {
  await login(page, 'e2e_teacher')
  for (const item of [
    ['班级管理', '班级管理'],
    ['教学管理', '教学管理'],
    ['作业管理', '作业管理'],
    ['测验管理', '测验管理'],
    ['课程答疑', '课程答疑'],
    ['数据概览', '教学数据'],
  ]) {
    await page.getByRole('link', { name: item[0], exact: true }).click()
    await expect(page.getByRole('heading', { name: item[1], exact: true })).toBeVisible()
    await expectStandardControlSizes(page)
  }
})


test('弹窗输入控件保留可见边框、焦点和校验状态', async ({ page }) => {
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '测验管理', exact: true }).click()
  await page.getByRole('button', { name: '＋ 创建测验', exact: true }).click()

  const dialog = page.getByRole('dialog', { name: '创建测验草稿' })
  const controlBorders = await dialog.locator(
    '.el-input__wrapper, .el-textarea__inner, .el-select__wrapper, .el-input-number',
  ).evaluateAll((elements) => elements.map((element) => {
    const style = getComputedStyle(element)
    const isNestedNumberInput = element.classList.contains('el-input__wrapper')
      && Boolean(element.closest('.el-input-number'))
    return {
      isNestedNumberInput,
      width: style.borderTopWidth,
      style: style.borderTopStyle,
    }
  }))
  expect(controlBorders.filter((control) => !control.isNestedNumberInput).every(
    (control) => control.width !== '0px' && control.style !== 'none',
  )).toBe(true)
  const singleLineControlHeights = await dialog.locator(
    '.el-input__wrapper, .el-select__wrapper, .el-input-number',
  ).evaluateAll((elements) => elements
    .filter((element) => !element.classList.contains('el-input__wrapper') || !element.closest('.el-input-number'))
    .map((element) => element.getBoundingClientRect().height))
  expect(singleLineControlHeights.every((height) => height >= 39.5)).toBe(true)
  await expectStandardControlSizes(dialog)

  const titleInput = dialog.getByPlaceholder('例如：第一章基础测验')
  await titleInput.focus()
  await expect(titleInput.locator('..')).toHaveCSS('border-top-color', 'rgb(40, 87, 127)')

  await dialog.getByRole('button', { name: '保存并添加试题', exact: true }).click()
  const invalidTitle = titleInput.locator('..')
  await expect(invalidTitle).toHaveCSS('border-top-color', 'rgb(245, 108, 108)')

  await page.setViewportSize({ width: 390, height: 844 })
  await expectNoHorizontalOverflow(page)
})


test('教师维护班级名册后学生可以查看所属班级', async ({ page }) => {
  const className = '端测软件工程一班'
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '班级管理', exact: true }).click()
  await page.getByRole('button', { name: '＋ 创建班级', exact: true }).click()

  let dialog = page.getByRole('dialog', { name: '创建班级' })
  await dialog.getByPlaceholder('例如：软件工程 2026 级一班').fill(className)
  await dialog.getByPlaceholder('填写年级、专业或教学安排等说明（可选）').fill('端到端班级名册验证')
  await dialog.getByRole('button', { name: '创建班级', exact: true }).click()
  await expect(page.getByText('班级创建成功')).toBeVisible()

  const classroomCard = page.locator('.classroom-card').filter({ hasText: className })
  const editButton = classroomCard.getByRole('button', { name: '编辑', exact: true })
  await expect(editButton).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
  await classroomCard.locator('.classroom-course-picker .el-select').click()
  await page.getByRole('option', { name: '端测基础课程（已发布）', exact: true }).click()
  await classroomCard.getByRole('button', { name: '关联课程', exact: true }).click()
  await expect(page.getByText('课程已关联，班级学生已同步加入')).toBeVisible()
  await expect(classroomCard.locator('.classroom-course-panel').getByText('端测基础课程', { exact: true })).toBeVisible()

  await editButton.click()
  dialog = page.getByRole('dialog', { name: '编辑班级' })
  await dialog.getByPlaceholder('填写年级、专业或教学安排等说明（可选）').fill('2026 秋季端到端班级')
  await dialog.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(classroomCard.getByText('2026 秋季端到端班级', { exact: true })).toBeVisible()

  await classroomCard.getByPlaceholder('学生用户名、学号或邮箱').fill('E2ES001')
  await classroomCard.getByRole('button', { name: '添加学生', exact: true }).click()
  await expect(page.getByText('学生已加入班级')).toBeVisible()
  await expect(classroomCard.getByText('端测学生', { exact: true })).toBeVisible()
  await expect(classroomCard.getByText('E2ES001', { exact: true })).toBeVisible()
  await expect(classroomCard.locator('.classroom-progress-panel')).toContainText('教学进展')
  await expect(classroomCard.locator('.classroom-course-progress-list')).toContainText('端测基础课程')

  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page).toHaveURL('/')
  await login(page, 'e2e_student')
  await page.getByRole('link', { name: '我的班级', exact: true }).click()
  const studentCard = page.locator('.classroom-card').filter({ hasText: className })
  await expect(studentCard.getByRole('link', { name: /端测教师.*查看主页/ })).toBeVisible()
  await expect(studentCard.getByText('2026 秋季端到端班级', { exact: true })).toBeVisible()
  await expect(studentCard.getByRole('link', { name: /端测基础课程/ })).toBeVisible()
  await expect(studentCard.locator('.el-table')).toHaveCount(0)
})


test('学生密码申请需由所属班级教师审批', async ({ page }) => {
  await page.goto('/login')
  await page.getByRole('button', { name: '忘记密码', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '找回密码' })
  await dialog.getByPlaceholder('请输入用户名').fill('e2e_student')
  await dialog.getByPlaceholder('注册邮箱、学号、工号或手机号').fill('E2ES001')
  await dialog.getByPlaceholder('8–72 位新密码').fill('PendingPassword123!')
  await dialog.getByPlaceholder('再次输入新密码').fill('PendingPassword123!')
  await dialog.getByRole('button', { name: '提交重置', exact: true }).click()
  await expect(page.getByText('申请已提交，请等待班级教师同意后使用新密码登录')).toBeVisible()

  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '班级管理', exact: true }).click()
  const resetPanel = page.locator('.classroom-reset-panel').filter({ hasText: '端测学生' })
  await expect(resetPanel).toBeVisible()
  await expect(resetPanel).toContainText('E2ES001')
  await resetPanel.getByRole('button', { name: '拒绝', exact: true }).click()
  const rejectDialog = page.getByRole('dialog', { name: '拒绝密码重置' })
  await rejectDialog.getByRole('button', { name: '确认拒绝', exact: true }).click()
  await expect(page.getByText('已拒绝密码重置申请')).toBeVisible()
  await expect(resetPanel).toBeHidden()
})


test('大量班级使用主从选择且移动端不会纵向复制名册', async ({ page }) => {
  await login(page, 'e2e_teacher')
  await page.route('**/api/statistics/classes/*', async (route) => {
    const classId = Number(new URL(route.request().url()).pathname.split('/').pop())
    await route.fulfill({
      json: {
        code: 0,
        message: 'success',
        data: {
          class_id: classId,
          class_name: `端测班级 ${classId}`,
          member_count: Math.max(0, (classId - 1000) * 3),
          course_count: 0,
          overview: {
            average_progress: 0,
            homework_submission_rate: 0,
            average_homework_percent: 0,
            exam_completion_rate: 0,
            average_exam_percent: 0,
            ready_video_count: 0,
            homework_count: 0,
            exam_count: 0,
          },
          courses: [],
        },
      },
    })
  })
  await page.route('**/api/classes', async (route) => {
    const response = await route.fetch()
    const payload = await response.json()
    const base = payload.data[0] || {
      teacher_name: '端测教师',
      teacher_no: 'E2ET001',
      created_at: '2026-09-12T00:00:00Z',
      students: [],
    }
    payload.data = Array.from({ length: 14 }, (_, index) => ({
      ...base,
      id: 1000 + index,
      name: `端测软件工程 ${String(index + 1).padStart(2, '0')} 班`,
      description: `第 ${index + 1} 个教学班`,
      member_count: index * 3,
      course_count: 0,
      courses: [],
    }))
    await route.fulfill({ response, json: payload })
  })

  await page.goto('/classes')
  await expect(page.locator('.classroom-list > button')).toHaveCount(14)
  await expect(page.locator('.classroom-card')).toHaveCount(1)
  const workspaceHeights = await Promise.all([
    page.locator('.classroom-list-panel').evaluate((element) => element.getBoundingClientRect().height),
    page.locator('.classroom-workspace > .classroom-card').evaluate((element) => element.getBoundingClientRect().height),
  ])
  expect(Math.abs(workspaceHeights[0] - workspaceHeights[1])).toBeLessThanOrEqual(1)
  expect(workspaceHeights[0]).toBeGreaterThanOrEqual(559)
  const listSize = await page.locator('.classroom-list').evaluate((element) => ({
    clientHeight: element.clientHeight,
    scrollHeight: element.scrollHeight,
  }))
  expect(listSize.scrollHeight).toBeGreaterThan(listSize.clientHeight)

  await page.locator('.classroom-list > button').nth(8).click()
  await expect(page.getByRole('heading', { name: '端测软件工程 09 班', exact: true })).toBeVisible()
  const heightAfterSelection = await page
    .locator('.classroom-list-panel')
    .evaluate((element) => element.getBoundingClientRect().height)
  expect(heightAfterSelection).toBe(workspaceHeights[0])

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.locator('.classroom-list-panel')).toBeHidden()
  await expect(page.locator('.classroom-mobile-selector')).toBeVisible()
  await expect(page.locator('.classroom-card')).toHaveCount(1)
  await expectNoHorizontalOverflow(page)
})


test('我的学习使用统一的卡片与操作控件尺寸', async ({ page }) => {
  await login(page, 'e2e_student')
  let includeFavorite = false
  await page.route('**/api/learning/courses', async (route) => {
    const response = await route.fetch()
    const payload = await response.json()
    const base = payload.data[0] || {
      id: 1,
      category_name: '计算机',
      join_time: '2026-09-12T00:00:00Z',
    }
    payload.data = [{
      ...base,
      id: 3001,
      name: 'C 语言程序设计',
      description: '从语法基础到程序设计实践，建立清晰的编程思维。',
      learning_progress: 26.15,
    }]
    await route.fulfill({ response, json: payload })
  })
  await page.route('**/api/learning/favorites', async (route) => {
    const response = await route.fetch()
    const payload = await response.json()
    payload.data = includeFavorite ? [{
      id: 3001,
      name: 'C 语言程序设计',
      description: '从语法基础到程序设计实践，建立清晰的编程思维。',
      category_name: '计算机',
    }] : []
    await route.fulfill({ response, json: payload })
  })

  await page.goto('/learning')
  const card = page.locator('.learning-course-card').first()
  await expect(card).toBeVisible()
  const metrics = await card.evaluate((element) => {
    const mark = element.querySelector('.learning-card-mark')
    const actions = [...element.querySelectorAll('.learning-card-actions > *')]
    return {
      cardWidth: element.getBoundingClientRect().width,
      cardHeight: element.getBoundingClientRect().height,
      markHeight: mark.getBoundingClientRect().height,
      actionHeights: actions.map((action) => action.getBoundingClientRect().height),
    }
  })
  expect(metrics.cardHeight).toBeGreaterThanOrEqual(209)
  expect(metrics.cardHeight).toBeLessThanOrEqual(211)
  expect(metrics.markHeight).toBeLessThan(metrics.cardHeight - 30)
  expect(metrics.actionHeights.every((height) => height >= 33.5)).toBe(true)
  const desktopTabWidth = await page.locator('.center-tabs').evaluate((element) => element.getBoundingClientRect().width)
  expect(desktopTabWidth).toBeLessThan(360)
  await expectStandardControlSizes(page)

  await page.getByRole('tab', { name: /我的收藏/ }).click()
  const emptyState = page.locator('.learning-empty')
  await expect(emptyState).toBeVisible()
  const emptyMetrics = await emptyState.evaluate((element) => ({
    width: element.getBoundingClientRect().width,
    height: element.getBoundingClientRect().height,
  }))
  expect(Math.abs(emptyMetrics.width - metrics.cardWidth)).toBeLessThanOrEqual(1)
  expect(Math.abs(emptyMetrics.height - metrics.cardHeight)).toBeLessThanOrEqual(1)

  includeFavorite = true
  await page.reload()
  await page.getByRole('tab', { name: /我的收藏/ }).click()
  const favoriteCard = page.locator('.favorite-card').first()
  await expect(favoriteCard).toBeVisible()
  const favoriteMetrics = await favoriteCard.evaluate((element) => ({
    width: element.getBoundingClientRect().width,
    height: element.getBoundingClientRect().height,
  }))
  expect(Math.abs(favoriteMetrics.width - metrics.cardWidth)).toBeLessThanOrEqual(1)
  expect(Math.abs(favoriteMetrics.height - metrics.cardHeight)).toBeLessThanOrEqual(1)

  await page.setViewportSize({ width: 390, height: 844 })
  await expectNoHorizontalOverflow(page)
  const mobileActionHeights = await card.locator('.learning-card-actions > *').evaluateAll(
    (elements) => elements.map((element) => element.getBoundingClientRect().height),
  )
  expect(mobileActionHeights.every((height) => height >= 39.5)).toBe(true)
})


test('管理员可以进入系统后台，角色路由不会泄露', async ({ page }) => {
  await login(page, 'e2e_admin')
  await page.getByRole('link', { name: '系统后台', exact: true }).click()
  await expect(page.getByRole('heading', { name: '系统后台', exact: true })).toBeVisible()
  await expect(page.getByText('视频处理中心', { exact: true })).toBeVisible()
  await expect(page.getByText('媒体工具可用', { exact: true })).toBeVisible()
  const adminColors = await page.locator(
    '.video-summary-grid strong, .video-runtime-bar, .operation-state, .file-presence, .admin-video-center .el-button',
  ).evaluateAll((elements) => elements.flatMap((element) => {
    const style = getComputedStyle(element)
    return [style.color, style.backgroundColor, style.borderColor]
  }))
  const isGrayScale = (color) => {
    const channels = color.match(/[\d.]+/g)?.map(Number) || []
    return channels.length < 3 || (channels[0] === channels[1] && channels[1] === channels[2])
  }
  expect(adminColors.every(isGrayScale)).toBe(true)
  const summaryBackgrounds = await page.locator('.video-summary-grid strong').evaluateAll(
    (elements) => elements.map((element) => getComputedStyle(element).backgroundColor),
  )
  expect(summaryBackgrounds.every((color) => color === 'rgba(0, 0, 0, 0)')).toBe(true)
  const refreshLabel = page.getByRole('button', { name: '刷新', exact: true }).locator('span')
  await expect(refreshLabel).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
  await expect(refreshLabel).toHaveCSS('padding-left', '0px')
  const pendingVideo = page.getByRole('row').filter({ hasText: '端测等待转码视频' })
  await pendingVideo.getByRole('button', { name: '终止转码', exact: true }).click()
  const cancelDialog = page.getByRole('dialog', { name: '终止转码任务' })
  await expect(cancelDialog).toContainText('原始视频文件会保留')
  await cancelDialog.getByRole('button', { name: '确认终止', exact: true }).click()
  await expect(pendingVideo.getByText('已终止', { exact: true })).toBeVisible()
  await expect(pendingVideo.getByRole('button', { name: '重新转码', exact: true })).toBeVisible()
  await expect(pendingVideo.getByRole('button', { name: '清理', exact: true })).toBeVisible()
  const failedVideo = page.getByRole('row').filter({ hasText: '端测失败转码视频' })
  await failedVideo.locator('summary').filter({ hasText: '查看错误原因' }).click()
  await expect(failedVideo.getByText('端到端模拟：转码进程异常退出')).toBeVisible()
  await failedVideo.getByRole('button', { name: '重新转码', exact: true }).click()
  const retryDialog = page.getByRole('dialog', { name: '重新转码' })
  await retryDialog.getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByText('视频重新转码完成')).toBeVisible({ timeout: 20_000 })
  await expect(failedVideo.getByText('可播放', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: /用户账号/ }).click()
  await expect(page.getByText('用户账号管理', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: /系统公告/ }).click()
  await expect(page.getByText('系统公告', { exact: true }).last()).toBeVisible()
  await page.getByRole('button', { name: /操作审计/ }).click()
  await expect(page.getByText('管理员操作审计', { exact: true })).toBeVisible()
  const retryAudit = page.getByRole('row').filter({ hasText: '重新处理视频' })
  await expect(retryAudit.getByText('重新转码', { exact: true })).toBeVisible()
  await expect(retryAudit).toContainText('e2e_admin')
  const cancelAudit = page.getByRole('row').filter({ hasText: '终止视频转码' })
  await expect(cancelAudit.getByText('终止转码', { exact: true })).toBeVisible()
  await expectStandardControlSizes(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole('button', { name: /视频处理/ }).click()
  await expectNoHorizontalOverflow(page)
  await page.getByRole('button', { name: /课程与班级/ }).click()
  await expectNoHorizontalOverflow(page)

  await page.goto('/teacher/courses')
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('link', { name: '系统后台', exact: true })).toBeVisible()
})


test('管理员切换账号角色后只提交当前角色编号', async ({ page }) => {
  await login(page, 'e2e_admin')
  await page.getByRole('link', { name: '系统后台', exact: true }).click()
  await page.getByRole('button', { name: /用户账号/ }).click()
  await page.getByRole('button', { name: '＋ 创建用户', exact: true }).click()

  const dialog = page.getByRole('dialog', { name: '创建教师或学生账号' })
  await dialog.getByPlaceholder('3–50 位字符').fill('e2e_role_switch_teacher')
  await dialog.getByPlaceholder('请输入姓名').fill('角色切换教师')
  await dialog.getByPlaceholder('至少 8 位').fill(password)
  await dialog.getByPlaceholder('请输入学号').fill('E2E-SWITCH-STUDENT')
  await dialog.getByText('教师', { exact: true }).click()
  await dialog.getByPlaceholder('请输入工号').fill('E2E-SWITCH-TEACHER')

  const createRequest = page.waitForRequest((request) =>
    request.url().endsWith('/api/admin/users') && request.method() === 'POST',
  )
  await dialog.getByRole('button', { name: '创建账号', exact: true }).click()
  const payload = (await createRequest).postDataJSON()
  expect(payload.teacher_no).toBe('E2E-SWITCH-TEACHER')
  expect(payload).not.toHaveProperty('student_no')
  await expect(page.getByText('用户账号已创建')).toBeVisible()
})


test('教师发布课程后学生可以浏览并加入', async ({ page }) => {
  const courseName = '端到端课程'
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '教学管理', exact: true }).click()

  await page.getByRole('button', { name: '＋ 创建课程' }).click()
  await page.getByPlaceholder('例如：高等数学基础').fill(courseName)
  await page.getByText('请选择课程分类', { exact: true }).click()
  await page.getByRole('option', { name: '端测分类' }).click()
  await page.getByPlaceholder('一句话介绍课程内容').fill('供浏览器自动化验证使用')
  const courseDialog = page.getByRole('dialog', { name: '创建课程' })
  await courseDialog.locator('input[type="file"][accept*="image"]')
    .setInputFiles({
      name: 'course-cover.png',
      mimeType: 'image/png',
      buffer: Buffer.from(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
        'base64',
      ),
    })
  await expect(courseDialog.locator('.course-cover-preview')).toHaveClass(/has-image/)
  await page.getByRole('button', { name: '保存课程', exact: true }).click()
  await expect(page.getByText('课程创建成功')).toBeVisible()

  let courseRow = page.getByRole('row').filter({ hasText: courseName })
  await courseRow.getByRole('button', { name: '添加章节' }).click()
  await page.getByPlaceholder('例如：第一章 课程导学').fill('第一章 自动化导学')
  await page.getByRole('button', { name: '保存章节', exact: true }).click()
  await expect(page.getByText('章节创建成功').last()).toBeVisible()
  await page.getByRole('dialog', { name: '编辑章节' }).getByRole('button', { name: '关闭', exact: true }).click()

  courseRow = page.getByRole('row').filter({ hasText: courseName })
  await courseRow.getByRole('button', { name: '发布课程' }).click()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(courseRow.getByText('已发布', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page).toHaveURL('/')
  await login(page, 'e2e_student')
  await page.getByRole('link', { name: '课程中心', exact: true }).click()
  const publishedCourseCard = page.locator('.course-card').filter({ hasText: courseName })
  await expect(publishedCourseCard.locator('.course-cover')).toHaveClass(/has-image/)
  await expect(publishedCourseCard.locator('.course-cover')).toHaveCSS(
    'background-image',
    /course_covers/,
  )
  await page.getByRole('link', { name: courseName, exact: true }).click()
  await expect(page.getByRole('heading', { name: courseName, exact: true })).toBeVisible()
  await expect(page.locator('.course-detail-hero')).toHaveClass(/has-cover/)
  const learningColumnHeights = await Promise.all([
    page.locator('.learning-layout > .player-panel').evaluate((element) => element.getBoundingClientRect().height),
    page.locator('.learning-layout > .chapter-panel').evaluate((element) => element.getBoundingClientRect().height),
  ])
  expect(Math.abs(learningColumnHeights[0] - learningColumnHeights[1])).toBeLessThanOrEqual(1)
  await page.getByRole('button', { name: /加入课程/ }).click()
  await expect(page.getByRole('button', { name: /已加入课程/ })).toBeVisible()

  await page.getByRole('link', { name: '我的学习', exact: true }).click()
  await expect(page.getByText(courseName, { exact: true })).toBeVisible()
  const learningCover = page.locator('.learning-course-card').filter({ hasText: courseName }).getByRole('img', { name: `${courseName}封面`, exact: true })
  await expect(learningCover).toBeVisible()
  await expect(learningCover).toHaveAttribute('src', /course_covers/)
  await expect.poll(() => learningCover.evaluate((image) => image.naturalWidth)).toBeGreaterThan(0)
  await expect(learningCover).toHaveCSS('object-fit', 'contain')
})


test('教师可以编辑课程章节并完成下线与重新发布', async ({ page }) => {
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '教学管理', exact: true }).click()

  await page.getByRole('button', { name: '＋ 创建课程' }).click()
  let dialog = page.getByRole('dialog', { name: '创建课程' })
  await dialog.getByPlaceholder('例如：高等数学基础').fill('课程生命周期草稿')
  await dialog.getByText('请选择课程分类', { exact: true }).click()
  await page.getByRole('option', { name: '端测分类' }).click()
  await dialog.getByPlaceholder('一句话介绍课程内容').fill('编辑前简介')
  await dialog.getByRole('button', { name: '保存课程', exact: true }).click()

  let courseRow = page.getByRole('row').filter({ hasText: '课程生命周期草稿' })
  await courseRow.getByRole('button', { name: '编辑', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '编辑课程' })
  await dialog.getByPlaceholder('例如：高等数学基础').fill('课程生命周期已编辑')
  await dialog.getByPlaceholder('一句话介绍课程内容').fill('编辑后简介')
  await dialog.getByRole('button', { name: '保存课程', exact: true }).click()
  await expect(page.getByText('课程信息已更新').last()).toBeVisible()

  courseRow = page.getByRole('row').filter({ hasText: '课程生命周期已编辑' })
  await courseRow.getByRole('button', { name: '添加章节', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '添加章节' })
  await dialog.getByPlaceholder('例如：第一章 课程导学').fill('生命周期章节')
  await dialog.getByRole('button', { name: '保存章节', exact: true }).click()
  await page.getByRole('dialog', { name: '编辑章节' }).getByRole('button', { name: '关闭', exact: true }).click()
  await courseRow.locator('.el-table__expand-icon').click()

  const chapterRow = page.locator('.chapter-row').filter({ hasText: '生命周期章节' })
  await chapterRow.getByRole('button', { name: '编辑', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '编辑章节' })
  await dialog.getByPlaceholder('例如：第一章 课程导学').fill('生命周期章节已编辑')
  await dialog.getByRole('button', { name: '保存章节', exact: true }).click()
  await expect(page.getByText('章节信息已更新')).toBeVisible()
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()

  courseRow = page.getByRole('row').filter({ hasText: '课程生命周期已编辑' })
  await courseRow.getByRole('button', { name: '发布课程', exact: true }).click()
  await page.getByRole('dialog', { name: '发布课程' }).getByRole('button', { name: '确定' }).click()
  await expect(courseRow.getByText('已发布', { exact: true })).toBeVisible()

  await courseRow.getByRole('button', { name: '编辑', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '编辑课程' })
  await expect(dialog.getByText('保存后的课程资料会立即对学生生效')).toBeVisible()
  await dialog.getByPlaceholder('例如：高等数学基础').fill('课程生命周期发布维护版')
  await dialog.getByRole('button', { name: '保存课程', exact: true }).click()
  await expect(page.getByText('课程信息已更新').last()).toBeVisible()

  courseRow = page.getByRole('row').filter({ hasText: '课程生命周期发布维护版' })
  await courseRow.getByRole('button', { name: '添加章节', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '添加章节' })
  await dialog.getByPlaceholder('例如：第一章 课程导学').fill('发布中新增章节')
  await dialog.getByRole('button', { name: '保存章节', exact: true }).click()
  await expect(page.getByText('章节创建成功').last()).toBeVisible()
  await page.getByRole('dialog', { name: '编辑章节' }).getByRole('button', { name: '关闭', exact: true }).click()

  courseRow = page.getByRole('row').filter({ hasText: '课程生命周期发布维护版' })
  await courseRow.getByRole('button', { name: '下线', exact: true }).click()
  await page.getByRole('dialog', { name: '下线课程' }).getByRole('button', { name: '确定' }).click()
  await expect(courseRow.getByText('已下线', { exact: true })).toBeVisible()

  await courseRow.getByRole('button', { name: '编辑', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '编辑课程' })
  await dialog.getByPlaceholder('例如：高等数学基础').fill('课程生命周期下线维护版')
  await dialog.getByPlaceholder('一句话介绍课程内容').fill('下线后完成内容维护')
  await dialog.getByRole('button', { name: '保存课程', exact: true }).click()
  await expect(page.getByText('课程信息已更新').last()).toBeVisible()

  courseRow = page.getByRole('row').filter({ hasText: '课程生命周期下线维护版' })
  await courseRow.getByRole('button', { name: '重新发布', exact: true }).click()
  await page.getByRole('dialog', { name: '重新发布课程' }).getByRole('button', { name: '确定' }).click()
  await expect(courseRow.getByText('已发布', { exact: true })).toBeVisible()
})


test('学生提交作业后教师可以批改并回传成绩', async ({ page }) => {
  const homeworkTitle = '端到端作业'
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '作业管理', exact: true }).click()

  await page.getByRole('button', { name: '＋ 创建作业' }).click()
  const createDialog = page.getByRole('dialog', { name: '创建作业草稿' })
  await createDialog.getByText('请选择课程', { exact: true }).click()
  await page.getByRole('option', { name: '端测基础课程（已发布）' }).click()
  await createDialog.getByPlaceholder('例如：第一章知识总结').fill(homeworkTitle)
  await createDialog.getByPlaceholder('说明完成要求、提交格式与评分要点…').fill('请提交自动化测试答案。')
  await createDialog.getByRole('button', { name: '保存草稿', exact: true }).click()
  await expect(page.getByText('作业草稿已创建')).toBeVisible()

  let homeworkCard = page.locator('.homework-card').filter({ hasText: homeworkTitle })
  await homeworkCard.getByRole('button', { name: '编辑', exact: true }).click()
  const editDialog = page.getByRole('dialog', { name: '编辑作业草稿' })
  await editDialog.getByPlaceholder('说明完成要求、提交格式与评分要点…').fill('修改后的自动化测试答案要求。')
  await editDialog.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(page.getByText('作业草稿已更新')).toBeVisible()

  homeworkCard = page.locator('.homework-card').filter({ hasText: homeworkTitle })
  await homeworkCard.getByRole('button', { name: '发布', exact: true }).click()
  await page.getByRole('dialog', { name: '发布作业' }).getByRole('button', { name: '确定' }).click()
  await expect(homeworkCard.getByText('进行中', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page).toHaveURL('/')
  await login(page, 'e2e_student')
  await page.getByRole('link', { name: '课程作业', exact: true }).click()
  homeworkCard = page.locator('.homework-card').filter({ hasText: homeworkTitle })
  await homeworkCard.getByRole('button', { name: '提交作业', exact: true }).click()
  const submissionDialog = page.getByRole('dialog', { name: homeworkTitle })
  await expectFixedDialog(page, submissionDialog)
  await submissionDialog.getByPlaceholder('请输入作业答案或总结…').fill('学生端到端答案')
  await submissionDialog.getByRole('button', { name: '确认提交', exact: true }).click()
  await expect(page.getByText('作业提交成功')).toBeVisible()
  await expect(homeworkCard.getByText('已提交', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page).toHaveURL('/')
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '作业管理', exact: true }).click()
  homeworkCard = page.locator('.homework-card').filter({ hasText: homeworkTitle })
  await homeworkCard.getByRole('button', { name: '查看提交（1）', exact: true }).click()
  const gradeDialog = page.getByRole('dialog', { name: `${homeworkTitle} · 提交记录` })
  await expect(gradeDialog.getByText('端测学生', { exact: true })).toBeVisible()
  await gradeDialog.getByRole('button', { name: '批改', exact: true }).click()
  await gradeDialog.getByRole('spinbutton').fill('88')
  await gradeDialog.getByPlaceholder('填写教师评语（可选）').fill('完成良好')
  await expectFixedDialog(page, gradeDialog)
  expect(await gradeDialog.getByRole('button', { name: '保存批改', exact: true }).locator('span').evaluate((element) => getComputedStyle(element).color)).toBe('rgb(255, 255, 255)')
  await gradeDialog.getByRole('button', { name: '保存批改', exact: true }).click()
  await expect(page.getByText('批改结果已保存')).toBeVisible()
  await expect(gradeDialog.getByText('88', { exact: true })).toBeVisible()

  await page.keyboard.press('Escape')
  await expect(gradeDialog).toBeHidden()
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page).toHaveURL('/')
  await login(page, 'e2e_student')
  await page.getByRole('link', { name: '课程作业', exact: true }).click()
  homeworkCard = page.locator('.homework-card').filter({ hasText: homeworkTitle })
  await expect(homeworkCard.getByText('88 分', { exact: true })).toBeVisible()
  await homeworkCard.getByRole('button', { name: '查看教师评语', exact: true }).click()
  const commentDialog = page.getByRole('dialog', { name: `${homeworkTitle} · 教师评语` })
  await expect(commentDialog.getByText('完成良好', { exact: true })).toBeVisible()
  await commentDialog.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(homeworkCard.locator('.submission-result-summary')).toContainText('已批改 · 不可修改')
  await expect(homeworkCard.locator('.homework-actions')).toHaveCount(0)
})


test('作业附件上传失败时重试不会重复创建草稿', async ({ page }) => {
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '作业管理', exact: true }).click()

  let createRequests = 0
  page.on('request', (request) => {
    if (request.url().endsWith('/api/homeworks') && request.method() === 'POST') {
      createRequests += 1
    }
  })
  await page.route(/\/api\/homeworks\/\d+\/attachment$/, (route) => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ code: 503, message: '附件服务暂不可用', data: null }),
  }))

  await page.getByRole('button', { name: '＋ 创建作业' }).click()
  const dialog = page.getByRole('dialog', { name: '创建作业草稿' })
  await dialog.getByText('请选择课程', { exact: true }).click()
  await page.getByRole('option', { name: '端测基础课程（已发布）' }).click()
  await dialog.getByPlaceholder('例如：第一章知识总结').fill('附件重试防重复草稿')
  await dialog.getByPlaceholder('说明完成要求、提交格式与评分要点…').fill('验证分阶段保存状态。')
  await dialog.locator('input[type="file"]').setInputFiles({
    name: '作业说明.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('attachment retry test'),
  })
  await dialog.getByRole('button', { name: '保存草稿', exact: true }).click()

  await expect(page.getByText(/作业草稿已创建，但附件上传失败/)).toBeVisible()
  await expect(dialog.getByText(/不会重复创建草稿/)).toBeVisible()
  await expect(dialog.getByRole('button', { name: '重试上传附件', exact: true })).toBeVisible()
  expect(createRequests).toBe(1)

  const retriedUpload = page.waitForResponse((response) =>
    /\/api\/homeworks\/\d+\/attachment$/.test(response.url()),
  )
  await dialog.getByRole('button', { name: '重试上传附件', exact: true }).click()
  expect((await retriedUpload).status()).toBe(503)
  expect(createRequests).toBe(1)
})


test('附件试卷无需在线题目即可发布提交和教师批改', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1366, height: 600 })
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '测验管理', exact: true }).click()
  await page.getByRole('button', { name: '＋ 创建测验' }).click()
  const createDialog = page.getByRole('dialog', { name: '创建测验草稿' })
  await createDialog.locator('label.el-radio').filter({ hasText: '附件试卷' }).click()
  await createDialog.getByText('请选择课程', { exact: true }).click()
  await page.getByRole('option', { name: '端测基础课程', exact: true }).click()
  await createDialog.getByPlaceholder('例如：第一章基础测验').fill('附件试卷直接发布')
  await createDialog.locator('input[type="file"]').setInputFiles({
    name: 'paper.txt', mimeType: 'text/plain', buffer: Buffer.from('Question 1: explain HTTP'),
  })
  await expectFixedDialog(page, createDialog)
  await createDialog.getByRole('button', { name: '保存并发布', exact: true }).click()
  await page.getByRole('dialog', { name: '发布测验', exact: true }).getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByText('测验已发布', { exact: true })).toBeVisible()
  await expect(page.getByRole('dialog', { name: '附件试卷直接发布 · 试题管理', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await login(page, 'e2e_student')
  await page.getByRole('link', { name: '在线测验', exact: true }).click()
  let card = page.locator('.exam-card').filter({ hasText: '附件试卷直接发布' })
  await card.getByRole('button', { name: '开始测验', exact: true }).click()
  const take = page.getByRole('dialog', { name: '附件试卷直接发布', exact: true })
  await take.getByPlaceholder('按题号填写答案，或上传答卷附件').fill('1. HTTP 是超文本传输协议。')
  await take.locator('input[type="file"]').setInputFiles({
    name: 'answer.txt', mimeType: 'text/plain', buffer: Buffer.from('Student attachment answer'),
  })
  await expect(take.getByText('已自动保存', { exact: true })).toBeVisible()
  await expectFixedDialog(page, take)
  expect(await take.locator('.el-dialog__body').evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true)
  await page.screenshot({ path: testInfo.outputPath('attachment-exam-student.png') })
  await take.getByRole('button', { name: '暂时离开', exact: true }).click()
  await card.getByRole('button', { name: '继续作答', exact: true }).click()
  await expect(take.getByPlaceholder('按题号填写答案，或上传答卷附件')).toHaveValue('1. HTTP 是超文本传输协议。')
  await expect(take.getByRole('button', { name: '查看已保存答卷附件', exact: true })).toBeVisible()
  await take.getByRole('button', { name: '提交测验', exact: true }).click()
  await expectCompactMessageBox(page)
  await page.getByRole('dialog', { name: '提交测验', exact: true }).getByRole('button', { name: '确定', exact: true }).click()
  await expect(take.getByText('已交卷，等待教师批改', { exact: true })).toBeVisible()
  await expect(take.getByRole('button', { name: '提交测验', exact: true })).toHaveCount(0)
  await take.getByRole('button', { name: '关闭', exact: true }).click()
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '测验管理', exact: true }).click()
  card = page.locator('.exam-card').filter({ hasText: '附件试卷直接发布' })
  await card.getByRole('button', { name: '答卷与批改（1）', exact: true }).click()
  const records = page.getByRole('dialog', { name: '附件试卷直接发布 · 成绩记录', exact: true })
  await records.getByRole('button', { name: '批改', exact: true }).click()
  await records.getByRole('spinbutton').fill('92')
  await records.getByPlaceholder('填写教师评语（可选）').fill('说明准确')
  await expectFixedDialog(page, records)
  expect(await records.getByRole('button', { name: '保存批改', exact: true }).locator('span').evaluate((element) => getComputedStyle(element).color)).toBe('rgb(255, 255, 255)')
  await records.getByRole('button', { name: '保存批改', exact: true }).click()
  await expect(records.getByText('92 / 100', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('attachment-exam-grading.png') })
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await login(page, 'e2e_student')
  await page.getByRole('link', { name: '在线测验', exact: true }).click()
  card = page.locator('.exam-card').filter({ hasText: '附件试卷直接发布' })
  await card.getByRole('button', { name: '查看结果', exact: true }).click()
  await expect(take.getByText('教师已批改', { exact: true })).toBeVisible()
  await expect(take.getByText('教师评语：说明准确', { exact: true })).toBeVisible()
  await expect(take.getByRole('textbox')).toHaveCount(0)
  await expect(take.getByRole('button', { name: '提交测验', exact: true })).toHaveCount(0)
})

test('附件试卷上传失败可以重试且不重复创建草稿', async ({ page }) => {
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '测验管理', exact: true }).click()
  let createRequests = 0
  page.on('request', (request) => {
    if (request.url().endsWith('/api/exams') && request.method() === 'POST') createRequests += 1
  })
  const attachmentRoute = /\/api\/exams\/\d+\/attachment$/
  await page.route(attachmentRoute, (route) => route.fulfill({
    status: 503, contentType: 'application/json',
    body: JSON.stringify({ code: 503, message: '附件服务暂不可用', data: null }),
  }))
  await page.getByRole('button', { name: '＋ 创建测验' }).click()
  const dialog = page.getByRole('dialog', { name: '创建测验草稿' })
  await dialog.locator('label.el-radio').filter({ hasText: '附件试卷' }).click()
  await dialog.getByText('请选择课程', { exact: true }).click()
  await page.getByRole('option', { name: '端测基础课程', exact: true }).click()
  await dialog.getByPlaceholder('例如：第一章基础测验').fill('测验附件失败重试')
  await dialog.locator('input[type="file"]').setInputFiles({
    name: 'reference.txt', mimeType: 'text/plain', buffer: Buffer.from('reference'),
  })
  await dialog.getByRole('button', { name: '保存并发布', exact: true }).click()
  await expect(page.getByText(/测验草稿已保存，但附件处理失败/)).toBeVisible()
  await expect(dialog.getByPlaceholder('例如：第一章基础测验')).toBeDisabled()
  expect(createRequests).toBe(1)
  await page.unroute(attachmentRoute)
  await dialog.getByRole('button', { name: '重试附件处理', exact: true }).click()
  const publishConfirm = page.getByRole('dialog', { name: '发布测验' })
  await expect(publishConfirm).toBeVisible()
  await publishConfirm.getByRole('button', { name: '确定', exact: true }).click()
  await expect(page.getByText('测验已发布')).toBeVisible()
  expect(createRequests).toBe(1)
  const card = page.locator('.exam-card').filter({ hasText: '测验附件失败重试' })
  await expect(card.getByText('附件试卷 · 教师批改', { exact: true })).toBeVisible()
  await expect(card.getByRole('button', { name: '测验附件', exact: true })).toBeVisible()
})

test('学生提交测验后教师可以查看自动评分结果', async ({ page }, testInfo) => {
  const examTitle = '端到端测验'
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '测验管理', exact: true }).click()

  await page.getByRole('button', { name: '＋ 创建测验' }).click()
  const createDialog = page.getByRole('dialog', { name: '创建测验草稿' })
  await createDialog.getByText('请选择课程', { exact: true }).click()
  await page.getByRole('option', { name: '端测基础课程', exact: true }).click()
  await createDialog.getByPlaceholder('例如：第一章基础测验').fill(examTitle)
  await createDialog.getByPlaceholder('填写作答要求…').fill('请选择正确答案。')
  await expect(createDialog.locator('.teaching-attachment-field')).toHaveCount(0)
  await createDialog.getByRole('button', { name: '保存并添加试题', exact: true }).click()
  await expect(page.getByText('测验草稿已创建，请继续添加试题')).toBeVisible()

  const questionDialog = page.getByRole('dialog', { name: `${examTitle} · 试题管理` }).locator('.el-dialog')
  await expect(questionDialog).toBeVisible()
  await page.setViewportSize({ width: 1366, height: 768 })
  const desktopPanel = await questionDialog.locator('.question-create-panel').boundingBox()
  expect(desktopPanel.width).toBeCloseTo(400, 0)
  await expect.poll(async () => {
    const box = await questionDialog.boundingBox()
    return Math.abs(box.y + box.height / 2 - 384)
  }).toBeLessThanOrEqual(0.2)
  const modalBefore = await questionDialog.boundingBox()
  expect(Math.abs(modalBefore.x + modalBefore.width / 2 - 683)).toBeLessThanOrEqual(2)
  expect(modalBefore.y).toBeGreaterThanOrEqual(15)
  expect(modalBefore.y + modalBefore.height).toBeLessThanOrEqual(753)
  expect(Math.abs(modalBefore.y + modalBefore.height / 2 - 384)).toBeLessThanOrEqual(2)
  await questionDialog.locator('.question-create-panel').hover()
  await page.mouse.wheel(0, 500)
  await expect.poll(() => questionDialog.locator('.question-create-panel').evaluate((element) => element.scrollTop)).toBeGreaterThan(0)
  const modalAfter = await questionDialog.boundingBox()
  expect(modalAfter.y).toBeCloseTo(modalBefore.y, 0)
  expect(await questionDialog.locator('.question-create-panel').evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  await questionDialog.locator('.question-create-panel').evaluate((element) => { element.scrollTop = 0 })
  await questionDialog.screenshot({ path: testInfo.outputPath('question-manager-desktop.png') })
  await page.setViewportSize({ width: 1100, height: 720 })
  expect((await questionDialog.locator('.question-create-panel').boundingBox()).width).toBeCloseTo(400, 0)
  await page.setViewportSize({ width: 390, height: 844 })
  await expect.poll(async () => {
    const box = await questionDialog.boundingBox()
    return Math.abs(box.y + box.height / 2 - 422) + Math.abs(box.x + box.width / 2 - 195)
  }).toBeLessThanOrEqual(2)
  expect(await questionDialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  await questionDialog.screenshot({ path: testInfo.outputPath('question-manager-mobile.png') })
  await page.setViewportSize({ width: 1366, height: 768 })
  const questionColumnHeights = await Promise.all([
    questionDialog.locator('.exam-question-list').evaluate((element) => element.getBoundingClientRect().height),
    questionDialog.locator('.question-create-panel').evaluate((element) => element.getBoundingClientRect().height),
  ])
  expect(Math.abs(questionColumnHeights[0] - questionColumnHeights[1])).toBeLessThanOrEqual(1)
  await questionDialog.getByPlaceholder('请输入题目内容').fill('HTTP 默认端口是多少？')
  await questionDialog.getByPlaceholder('选项 A').fill('80')
  await questionDialog.getByPlaceholder('选项 B').fill('443')
  await questionDialog.locator('.question-number-row input[role="spinbutton"]').first().fill('100')
  await questionDialog.getByRole('button', { name: '添加到测验', exact: true }).click()
  await expect(page.getByText('试题已添加')).toBeVisible()
  const questionItem = questionDialog.locator('.exam-question-list article').filter({ hasText: 'HTTP 默认端口是多少？' })
  await questionItem.getByRole('button', { name: '编辑', exact: true }).click()
  await questionDialog.getByPlaceholder('请输入题目内容').fill('HTTP 协议的默认端口是多少？')
  await questionDialog.getByRole('button', { name: '保存试题修改', exact: true }).click()
  await expect(page.getByText('试题已更新')).toBeVisible()
  await expect(questionDialog.getByText('HTTP 协议的默认端口是多少？', { exact: true })).toBeVisible()
  await questionDialog.getByRole('button', { name: '稍后继续', exact: true }).click()
  await expect(questionDialog).toBeHidden()

  const draftExamCard = page.locator('.exam-card').filter({ hasText: examTitle })
  await draftExamCard.getByRole('button', { name: '编辑信息', exact: true }).click()
  const editExamDialog = page.getByRole('dialog', { name: '编辑测验草稿' })
  await editExamDialog.getByPlaceholder('填写作答要求…').fill('修改后的作答要求。')
  await editExamDialog.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(page.getByText('测验草稿已更新')).toBeVisible()
  await draftExamCard.getByRole('button', { name: '试题管理', exact: true }).click()

  await expect(questionDialog.getByText('分值已匹配，可以发布')).toBeVisible()
  await questionDialog.getByRole('button', { name: '发布测验', exact: true }).click()
  await page.getByRole('dialog', { name: '发布测验' }).getByRole('button', { name: '确定' }).click()
  await expect(page.getByText('测验已发布')).toBeVisible()

  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page).toHaveURL('/')
  await login(page, 'e2e_student')
  await page.getByRole('link', { name: '在线测验', exact: true }).click()
  let examCard = page.locator('.exam-card').filter({ hasText: examTitle })
  await expect(examCard.getByRole('button', { name: '测验附件', exact: true })).toHaveCount(0)
  await examCard.getByRole('button', { name: '开始测验', exact: true }).click()
  const takeDialog = page.getByRole('dialog', { name: examTitle })
  const answerSaved = page.waitForResponse((response) => (
    /\/api\/exams\/\d+\/answers$/.test(response.url())
    && response.request().method() === 'PUT'
  ))
  await takeDialog.locator('label.el-radio').filter({ hasText: '80' }).click()
  expect((await answerSaved).status()).toBe(200)
  await expect(takeDialog.getByText('已自动保存', { exact: true })).toBeVisible()
  await takeDialog.getByRole('button', { name: '提交测验', exact: true }).click()
  await expectCompactMessageBox(page)
  await page.screenshot({ path: testInfo.outputPath('exam-submit-confirmation.png') })
  await page.getByRole('dialog', { name: '提交测验' }).getByRole('button', { name: '确定' }).click()
  await expect(page.getByText('交卷成功，得分 100')).toBeVisible()
  await expect(takeDialog.locator('.result-score strong')).toHaveText('100')

  await takeDialog.getByRole('button', { name: '关闭', exact: true }).click()
  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page).toHaveURL('/')
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '测验管理', exact: true }).click()
  examCard = page.locator('.exam-card').filter({ hasText: examTitle })
  await examCard.getByRole('button', { name: '成绩（1）', exact: true }).click()
  const recordsDialog = page.getByRole('dialog', { name: `${examTitle} · 成绩记录` })
  await expect(recordsDialog.getByText('端测学生', { exact: true })).toBeVisible()
  await expect(recordsDialog.getByText('100 / 100', { exact: true })).toBeVisible()
})


test('网络故障时显示中文提示且页面保持可用', async ({ page }) => {
  await login(page, 'e2e_student')
  await page.route('**/api/homeworks', (route) => route.abort())
  await page.getByRole('link', { name: '课程作业', exact: true }).click()

  await expect(page.getByRole('heading', { name: '课程作业', exact: true })).toBeVisible()
  await expect(page.locator('.el-result__subtitle')).toHaveText('网络连接失败，请检查网络或服务状态')
  await expect(page.locator('.homework-grid')).toHaveCount(0)
  await page.unroute('**/api/homeworks')
  await page.getByRole('button', { name: '重新加载', exact: true }).click()
  await expect(page.locator('.el-result')).toHaveCount(0)
  await expect(page.locator('.homework-grid')).toBeVisible()
})


test('视频资源加载失败时显示中文错误并支持重试', async ({ page }) => {
  await login(page, 'e2e_student')
  const playlistPattern = /\/media\/videos\/hls\/e2e\/index\.m3u8$/
  await page.route(playlistPattern, (route) => route.fulfill({
    status: 503,
    contentType: 'application/vnd.apple.mpegurl',
    body: '',
  }))

  await page.goto('/courses/1')
  const playbackError = page.getByRole('alert')
  await expect(playbackError).toContainText('视频资源暂时无法加载', { timeout: 20_000 })

  await page.unroute(playlistPattern)
  await playbackError.getByRole('button', { name: '重新加载视频', exact: true }).click()
  const video = page.locator('video')
  await expect(video).toBeVisible()
  await expect.poll(
    () => video.evaluate((element) => element.readyState),
    { timeout: 15_000 },
  ).toBeGreaterThanOrEqual(1)
})


test('项目内 FFmpeg 生成的 HLS 可以在 Chromium 中播放', async ({ page }) => {
  await login(page, 'e2e_student')
  await page.getByRole('link', { name: '课程中心', exact: true }).click()
  const playlistResponse = page.waitForResponse((response) =>
    response.url().endsWith('/index.m3u8'),
  )
  await page.getByRole('link', { name: '端测基础课程', exact: true }).click()
  expect((await playlistResponse).ok()).toBe(true)

  const video = page.locator('video')
  await expect(video).toBeVisible()
  await expect.poll(
    () => video.evaluate((element) => element.readyState),
    { timeout: 15000 },
  ).toBeGreaterThanOrEqual(1)
  await video.evaluate(async (element) => {
    element.muted = true
    await element.play()
  })
  await expect.poll(
    () => video.evaluate((element) => element.currentTime),
    { timeout: 15000 },
  ).toBeGreaterThan(0.25)
})


test('教师上传视频时拒绝错误格式并完成真实 MP4 转码', async ({ page }) => {
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '教学管理', exact: true }).click()
  const courseRow = page.getByRole('row').filter({ hasText: '端测视频上传草稿' })
  await courseRow.locator('.el-table__expand-icon').click()
  const chapterRow = page.locator('.chapter-row').filter({ hasText: '上传测试章节' })
  await chapterRow.getByRole('button', { name: '上传视频', exact: true }).click()

  const dialog = page.getByRole('dialog', { name: '编辑章节' })
  await dialog.getByPlaceholder('请输入视频标题').fill('浏览器上传视频')
  await dialog.locator('input[type="file"]').setInputFiles({
    name: '错误格式.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('not a video'),
  })
  const rejectedResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/videos/upload'),
  )
  await dialog.getByRole('button', { name: '上传并处理', exact: true }).click()
  expect((await rejectedResponse).status()).toBe(400)
  await expect(page.getByText('不支持的视频格式')).toBeVisible()

  await dialog.locator('input[type="file"]').setInputFiles(uploadFixture)
  const uploadedResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/videos/upload'),
  )
  await dialog.getByRole('button', { name: '上传并处理', exact: true }).click()
  expect((await uploadedResponse).status()).toBe(201)
  await expect(page.getByText('视频处理完成')).toBeVisible()
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  await courseRow.getByRole('button', { name: '展开当前行' }).click()
  await expect(page.getByText('浏览器上传视频 · 可播放', { exact: true })).toBeVisible()

  await chapterRow.getByRole('button', { name: '编辑', exact: true }).click()
  let manageDialog = page.getByRole('dialog', { name: '编辑章节' })
  let videoRow = manageDialog.locator('.chapter-editor-video').filter({ hasText: '浏览器上传视频' })
  await videoRow.getByRole('button', { name: '编辑视频', exact: true }).click()
  await manageDialog.getByPlaceholder('请输入视频标题').fill('浏览器更新视频')
  const editedResponse = page.waitForResponse((response) =>
    /\/api\/videos\/\d+$/.test(new URL(response.url()).pathname) && response.request().method() === 'PUT',
  )
  await manageDialog.getByRole('button', { name: '保存修改', exact: true }).click()
  expect((await editedResponse).status()).toBe(200)
  await expect(page.getByText('视频资料已更新')).toBeVisible()
  await expect(manageDialog.locator('.chapter-editor-video').filter({ hasText: '浏览器更新视频' })).toHaveCount(1)
  await expect(manageDialog.locator('.chapter-video-form')).toHaveCount(0)

  videoRow = manageDialog.locator('.chapter-editor-video').filter({ hasText: '浏览器更新视频' })
  await videoRow.getByRole('button', { name: '替换文件', exact: true }).click()
  await manageDialog.locator('input[type="file"]').setInputFiles(uploadFixture)
  const replacedResponse = page.waitForResponse((response) =>
    /\/api\/videos\/\d+\/replace$/.test(new URL(response.url()).pathname),
  )
  await manageDialog.getByRole('button', { name: '替换并处理', exact: true }).click()
  await page.getByRole('dialog', { name: '确认替换视频' })
    .getByRole('button', { name: '确认替换', exact: true }).click()
  expect((await replacedResponse).status()).toBe(201)
  await expect(page.getByText('视频替换完成')).toBeVisible()
  await expect(manageDialog.locator('.chapter-video-form')).toHaveCount(0)

  videoRow = manageDialog.locator('.chapter-editor-video').filter({ hasText: '浏览器更新视频' })
  const deletedResponse = page.waitForResponse((response) =>
    /\/api\/videos\/\d+$/.test(new URL(response.url()).pathname) && response.request().method() === 'DELETE',
  )
  await videoRow.getByRole('button', { name: '删除视频', exact: true }).click()
  await page.getByRole('dialog', { name: '删除视频' })
    .getByRole('button', { name: '确认删除', exact: true }).click()
  expect((await deletedResponse).status()).toBe(200)
  await expect(page.getByText('视频已删除')).toBeVisible()
})


test('长课程文本在移动端卡片内换行且业务页面无横向溢出', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page, 'e2e_student')

  for (const item of [
    ['课程中心', '发现适合你的课程'],
    ['我的学习', '我的学习'],
    ['我的班级', '我的班级'],
    ['课程作业', '课程作业'],
    ['在线测验', '在线测验'],
    ['数据概览', '学习数据'],
  ]) {
    await page.getByRole('link', { name: item[0], exact: true }).click()
    await expect(page.getByRole('heading', { name: item[1], exact: true })).toBeVisible()
    await expectNoHorizontalOverflow(page)
  }

  await page.getByRole('link', { name: '课程中心', exact: true }).click()
  const longCard = page.locator('.course-card').filter({ hasText: '端测超长课程名称' })
  await expect(longCard).toBeVisible()
  const textOverflows = await longCard.locator('h2, .course-description').evaluateAll((elements) =>
    elements.map((element) => element.scrollWidth > element.clientWidth),
  )
  expect(textOverflows).toEqual([false, false])
})


test('大量课程每页固定九门、课程区不独立滚动且移动端分页器不溢出', async ({ page }) => {
  await page.route('**/api/courses', async (route) => {
    const response = await route.fetch()
    const payload = await response.json()
    const base = payload.data[0] || {
      category_name: '端测分类',
      teacher_name: '端测教师',
      description: '用于验证大量课程的分页布局。',
    }
    payload.data = Array.from({ length: 25 }, (_, index) => ({
      ...base,
      id: 2000 + index,
      name: `端测分页课程 ${String(index + 1).padStart(2, '0')}`,
    }))
    await route.fulfill({ response, json: payload })
  })

  await page.goto('/courses')
  await expect(page.locator('.course-card')).toHaveCount(9)
  const pager = page.getByLabel('课程列表分页')
  await expect(pager).toBeVisible()
  await expect.poll(() => page.locator('.course-grid').evaluate((element) => getComputedStyle(element).overflowY)).toBe('visible')
  expect(await page.evaluate(() => document.documentElement.scrollHeight > window.innerHeight)).toBe(true)
  await pager.getByText('3', { exact: true }).click()
  await expect(page.getByRole('link', { name: '端测分页课程 19', exact: true })).toBeVisible()
  await expect(page.locator('.course-card')).toHaveCount(7)

  await page.setViewportSize({ width: 390, height: 844 })
  await expectNoHorizontalOverflow(page)
})


test('无学习记录的学生可以看到明确空状态', async ({ page }) => {
  await login(page, 'e2e_empty_student')
  await page.getByRole('link', { name: '我的学习', exact: true }).click()
  await expect(page.getByText('还没有加入课程，先去课程中心看看吧')).toBeVisible()

  await page.getByRole('link', { name: '课程作业', exact: true }).click()
  await expect(page.getByText('当前没有需要完成的课程作业')).toBeVisible()

  await page.getByRole('link', { name: '在线测验', exact: true }).click()
  await expect(page.getByText('当前没有可参加的课程测验')).toBeVisible()
})


test('慢速课程请求期间显示加载反馈并在完成后恢复内容', async ({ page }) => {
  await login(page, 'e2e_student')
  await page.route(/\/api\/courses(?:\?.*)?$/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 800))
    await route.continue()
  })

  await page.getByRole('link', { name: '课程中心', exact: true }).click()
  await expect(page.getByText('正在加载课程…')).toBeVisible()
  await expect(page.getByText(/^共 \d+ 门课程$/)).toBeVisible()
  await expect(page.locator('.course-grid .el-loading-mask')).toBeHidden()
})


test('移动端登录页无横向溢出且可以正常登录', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/login')
  await expect(page.getByPlaceholder('请输入登录密码')).toBeVisible()
  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  )
  expect(hasHorizontalOverflow).toBe(false)

  await page.getByPlaceholder('用户名、邮箱、学号或工号').fill('e2e_student')
  await page.getByPlaceholder('请输入登录密码').fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL('/')
})
