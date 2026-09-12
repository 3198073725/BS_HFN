import { expect, test } from '@playwright/test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'


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
  const refreshedAccessToken = await page.evaluate(() => localStorage.getItem('access_token'))
  expect(refreshedAccessToken).not.toBe('invalid-token')
  expect(refreshedAccessToken).toBeTruthy()
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


test('学生可以访问学习、作业、测验和数据页面', async ({ page }) => {
  await login(page, 'e2e_student')
  for (const item of [
    ['我的学习', '我的学习'],
    ['课程作业', '课程作业'],
    ['在线测验', '在线测验'],
    ['数据概览', '学习数据'],
  ]) {
    await page.getByRole('link', { name: item[0], exact: true }).click()
    await expect(page.getByRole('heading', { name: item[1], exact: true })).toBeVisible()
  }
})


test('教师可以访问教学、作业、测验、答疑和数据页面', async ({ page }) => {
  await login(page, 'e2e_teacher')
  for (const item of [
    ['教学管理', '教学管理'],
    ['作业管理', '作业管理'],
    ['测验管理', '测验管理'],
    ['课程答疑', '课程答疑'],
    ['数据概览', '教学数据'],
  ]) {
    await page.getByRole('link', { name: item[0], exact: true }).click()
    await expect(page.getByRole('heading', { name: item[1], exact: true })).toBeVisible()
  }
})


test('管理员可以进入系统后台，角色路由不会泄露', async ({ page }) => {
  await login(page, 'e2e_admin')
  await page.getByRole('link', { name: '系统后台', exact: true }).click()
  await expect(page.getByRole('heading', { name: '系统后台', exact: true })).toBeVisible()

  await page.goto('/teacher/courses')
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('link', { name: '系统后台', exact: true })).toBeVisible()
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
  await page.getByRole('button', { name: '保存课程', exact: true }).click()
  await expect(page.getByText('课程创建成功')).toBeVisible()

  let courseRow = page.getByRole('row').filter({ hasText: courseName })
  await courseRow.getByRole('button', { name: '添加章节' }).click()
  await page.getByPlaceholder('例如：第一章 课程导学').fill('第一章 自动化导学')
  await page.getByRole('button', { name: '保存章节', exact: true }).click()
  await expect(page.getByText('章节创建成功')).toBeVisible()

  courseRow = page.getByRole('row').filter({ hasText: courseName })
  await courseRow.getByRole('button', { name: '发布课程' }).click()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await expect(courseRow.getByText('已发布', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page).toHaveURL('/')
  await login(page, 'e2e_student')
  await page.getByRole('link', { name: '课程中心', exact: true }).click()
  await page.getByRole('link', { name: courseName, exact: true }).click()
  await expect(page.getByRole('heading', { name: courseName, exact: true })).toBeVisible()
  await page.getByRole('button', { name: /加入课程/ }).click()
  await expect(page.getByRole('button', { name: /已加入课程/ })).toBeVisible()

  await page.getByRole('link', { name: '我的学习', exact: true }).click()
  await expect(page.getByText(courseName, { exact: true })).toBeVisible()
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
  await expect(homeworkCard.getByText('教师评语：完成良好', { exact: true })).toBeVisible()
})


test('学生提交测验后教师可以查看自动评分结果', async ({ page }) => {
  const examTitle = '端到端测验'
  await login(page, 'e2e_teacher')
  await page.getByRole('link', { name: '测验管理', exact: true }).click()

  await page.getByRole('button', { name: '＋ 创建测验' }).click()
  const createDialog = page.getByRole('dialog', { name: '创建测验草稿' })
  await createDialog.getByText('请选择课程', { exact: true }).click()
  await page.getByRole('option', { name: '端测基础课程', exact: true }).click()
  await createDialog.getByPlaceholder('例如：第一章基础测验').fill(examTitle)
  await createDialog.getByPlaceholder('填写作答要求…').fill('请选择正确答案。')
  await createDialog.getByRole('button', { name: '保存并添加试题', exact: true }).click()
  await expect(page.getByText('测验草稿已创建，请继续添加试题')).toBeVisible()

  const questionDialog = page.getByRole('dialog', { name: `${examTitle} · 试题管理` })
  await questionDialog.getByPlaceholder('请输入题目内容').fill('HTTP 默认端口是多少？')
  await questionDialog.getByPlaceholder('选项 A').fill('80')
  await questionDialog.getByPlaceholder('选项 B').fill('443')
  await questionDialog.locator('.question-number-row input[role="spinbutton"]').first().fill('100')
  await questionDialog.getByRole('button', { name: '添加到测验', exact: true }).click()
  await expect(page.getByText('试题已添加')).toBeVisible()
  await expect(questionDialog.getByText('分值已匹配，可以发布')).toBeVisible()
  await questionDialog.getByRole('button', { name: '发布测验', exact: true }).click()
  await page.getByRole('dialog', { name: '发布测验' }).getByRole('button', { name: '确定' }).click()
  await expect(page.getByText('测验已发布')).toBeVisible()

  await page.getByRole('button', { name: '退出', exact: true }).click()
  await expect(page).toHaveURL('/')
  await login(page, 'e2e_student')
  await page.getByRole('link', { name: '在线测验', exact: true }).click()
  let examCard = page.locator('.exam-card').filter({ hasText: examTitle })
  await examCard.getByRole('button', { name: '开始测验', exact: true }).click()
  const takeDialog = page.getByRole('dialog', { name: examTitle })
  await takeDialog.locator('label.el-radio').filter({ hasText: '80' }).click()
  await takeDialog.getByRole('button', { name: '提交测验', exact: true }).click()
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
  await expect(page.getByText('网络连接失败，请检查网络或服务状态')).toBeVisible()
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

  const dialog = page.getByRole('dialog', { name: '上传视频' })
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
  await courseRow.getByRole('button', { name: '展开当前行' }).click()
  await expect(page.getByText('浏览器上传视频 · 可播放', { exact: true })).toBeVisible()
})


test('长课程文本在移动端卡片内换行且业务页面无横向溢出', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page, 'e2e_student')

  for (const item of [
    ['课程中心', '发现适合你的课程'],
    ['我的学习', '我的学习'],
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
