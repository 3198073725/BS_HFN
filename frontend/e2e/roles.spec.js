import { expect, test } from '@playwright/test'


const password = 'E2ePassword123!'


async function login(page, account) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名、邮箱、学号或工号').fill(account)
  await page.getByPlaceholder('请输入登录密码').fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('button', { name: '退出' })).toBeVisible()
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
