import { expect, test } from '@playwright/test'
import { resolve } from 'node:path'

const pause = (ms) => new Promise((done) => setTimeout(done, ms))
const pagination = (total = 0, page = 1, page_size = 20) => ({ total, page, page_size })
const pageErrors = new WeakMap()
test.beforeEach(async ({ page }) => {
  const errors = []
  pageErrors.set(page, errors)
  page.on('pageerror', (error) => errors.push(error.message))
})
test.afterEach(async ({ page }) => { expect(pageErrors.get(page)).toEqual([]) })
async function isolate(page, role, handler = () => null) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'isolated-focus'))
  await page.route(/https?:\/\/[^/]+\/api\//, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const result = await handler(url, request) || {}
    if (result.raw != null) {
      await route.fulfill({ contentType: 'text/plain', body: result.raw })
      return
    }
    const defaults = url.pathname === '/api/users/me' ? { id: 1, role, real_name: '测试用户' }
      : url.pathname.includes('/notifications') ? { items: [], unread_count: 0, pagination: pagination(0, 1, 12) }
        : ['/api/admin/videos', '/api/admin/users', '/api/admin/courses', '/api/admin/audit-logs'].includes(url.pathname)
          ? { items: [], summary: {}, runtime: {}, pagination: pagination() }
          : url.pathname === '/api/statistics' ? {} : []
    await route.fulfill({ status: result.status || 200, contentType: 'application/json',
      body: JSON.stringify({ code: result.status || 200, data: result.data ?? defaults }) })
  })
}
const notice = { id: 1, title: '公告全文', content: '完整正文\n第二段说明', publish_time: '2026-09-13T00:00:00' }

test('公告关闭恢复原按钮；直接链接没有入口时恢复页面标题', async ({ page }) => {
  await isolate(page, 'STUDENT', (url) => url.pathname === '/api/notices' ? { data: [notice] } : null)
  await page.goto('/notices')
  const opener = page.getByRole('button', { name: '阅读全文', exact: true })
  await opener.focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('dialog', { name: notice.title })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(opener).toBeFocused()
  await page.goto('/notices?notice_id=1')
  await expect(page.getByRole('dialog', { name: notice.title })).toBeVisible()
  await page.getByRole('dialog', { name: notice.title }).getByRole('button', { name: '关闭', exact: true }).click()
  await expect(page.getByRole('heading', { name: '通知公告', exact: true })).toBeFocused()
})

test('批改记录长正文支持键盘全文；嵌套附件关闭回到预览入口，外层关闭回到查看提交', async ({ page }) => {
  const homework = { id: 1, title: '测试作业', description: '要求', course_name: '课程', status: 'PUBLISHED', total_score: 100,
    submission_count: 1, deadline: '2099-01-01T00:00:00' }
  const content = '提交正文包含完整推导过程。'.repeat(80) + '【正文终点】'
  await isolate(page, 'TEACHER', (url) => {
    if (url.pathname === '/api/homeworks/manage') return { data: [homework] }
    if (url.pathname === '/api/homeworks/1/submissions') return { data: [{ id: 2, student_name: '学生', content, attachment: 'answer.txt', status: 'SUBMITTED' }] }
    if (url.pathname === '/api/homeworks/submissions/2/attachment') return { raw: '附件正文' }
  })
  await page.goto('/homeworks')
  const opener = page.getByRole('button', { name: /查看提交/ })
  await opener.click()
  const outer = page.getByRole('dialog', { name: '测试作业 · 提交记录' })
  const summary = outer.locator('summary[aria-label="查看提交内容全文"]')
  await summary.focus()
  await page.keyboard.press('Enter')
  await expect(outer.locator('.overflow-text-full')).toBeVisible()
  await expect(outer.locator('.overflow-text-full')).toContainText('【正文终点】')
  await page.keyboard.press('Tab')
  await expect(outer.locator('.overflow-text-full')).toBeFocused()
  const preview = outer.getByRole('button', { name: '预览附件', exact: true })
  await preview.click()
  const nested = page.getByRole('dialog', { name: '学生的提交附件.txt' })
  await expect(nested.locator('iframe')).toBeVisible()
  await nested.getByRole('button', { name: '关闭', exact: true }).click()
  await expect(preview).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(opener).toBeFocused()
})

for (const count of [1, 13]) {
  test(`只看未读${count}条：最后一条移除后焦点与页码有效`, async ({ page }) => {
    let items = Array.from({ length: count }, (_, n) => ({ id: n + 1, title: `通知${n + 1}`, content: '说明', category: 'CLASS', read: false, sender_name: '教师' }))
    await isolate(page, 'STUDENT', async (url, request) => {
      if (/\/notifications\/\d+\/read$/.test(url.pathname)) {
        await pause(300)
        items = items.filter((item) => item.id !== Number(url.pathname.split('/')[3]))
        return { data: {} }
      }
      if (url.pathname === '/api/notifications') {
        const current = Number(url.searchParams.get('page') || 1)
        return { data: { items: items.slice((current - 1) * 12, current * 12), unread_count: items.length, pagination: pagination(items.length, current, 12) } }
      }
    })
    await page.goto('/notifications')
    const filter = page.getByRole('switch')
    await filter.focus()
    await page.keyboard.press('Space')
    await expect(filter).toBeChecked()
    await expect(filter).toHaveAttribute('aria-checked', 'true')
    if (count === 13) {
      const pager = page.locator('.notification-list .el-pagination')
      const firstPageY = await pager.evaluate((element) => element.getBoundingClientRect().top + window.scrollY)
      await page.locator('.el-pager li.number').filter({ hasText: /^2$/ }).click()
      await expect(page.locator('.notification-item')).toHaveCount(1)
      const lastPageY = await pager.evaluate((element) => element.getBoundingClientRect().top + window.scrollY)
      expect(Math.abs(lastPageY - firstPageY)).toBeLessThan(1)
    }
    await expect(page.locator('.notification-item')).toHaveCount(1)
    await page.locator('.notification-item').focus()
    await page.keyboard.press('Enter')
    if (count === 1) {
      await expect(page.locator('.notification-item')).toHaveCount(0)
      await expect(filter).toBeFocused()
      await expect(page.getByText('暂时没有通知', { exact: true })).toBeVisible()
    } else {
      await expect(page.locator('.notification-item')).toHaveCount(12)
      await expect(page.locator('.notification-item').first()).toBeFocused()
      await expect(page.locator('.el-pagination')).toHaveCount(0)
    }
  })
}

test('慢速标为已读不抢夺用户移动后的焦点；全部已读按钮失效时焦点有落点', async ({ page }) => {
  let count = 1
  await isolate(page, 'STUDENT', async (url, request) => {
    if (request.method() === 'PUT') { await pause(500); count = 0; return { data: {} } }
    if (url.pathname === '/api/notifications') return { data: { items: [{ id: 1, title: '系统提示', content: '说明', read: !count }], unread_count: count, pagination: pagination(1, 1, 12) } }
  })
  await page.goto('/notifications')
  await page.locator('.notification-item').click()
  const navigation = page.getByRole('link', { name: '课程中心', exact: true })
  await navigation.focus()
  await expect(page.getByRole('button', { name: '全部标为已读' })).toBeDisabled()
  await expect(navigation).toBeFocused()
  count = 1
  await page.reload()
  const all = page.getByRole('button', { name: '全部标为已读' })
  await all.click()
  await expect(all).toBeDisabled()
  await expect(page.locator('.notification-item')).toBeFocused()
})

for (const width of [390, 1440]) {
  for (const count of [0, 1, 30]) {
    test(`分类${count}条、视口${width}：短名称不多余入口，长名称全文与列表内部滚动`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      const name = '跨学科综合课程分类名称'.repeat(4)
      const description = '分类说明含教学范围与适用对象。'.repeat(18) + '【说明终点】'
      const items = Array.from({ length: count }, (_, n) => ({ id: n + 1, name: n ? '短名称' : name, description: n ? '简述' : description,
        sort_order: n, status: 1, course_count: n, updated_at: '2026-09-13T00:00:00' }))
      await isolate(page, 'ADMIN', (url) => url.pathname === '/api/admin/categories' ? { data: items } : null)
      await page.goto('/admin')
      await page.getByRole('button', { name: /^课程分类/ }).click()
      if (!count) {
        await expect(page.getByText('暂无课程分类', { exact: true })).toBeVisible()
      } else {
        await expect(page.locator('summary[aria-label="查看分类名称全文"]')).toHaveCount(width === 390 ? 1 : 0)
        if (width === 1440 && count === 1) {
          await page.setViewportSize({ width: 390, height: 900 })
          await expect(page.locator('summary[aria-label="查看分类名称全文"]')).toHaveCount(1)
          await page.setViewportSize({ width, height: 900 })
          await expect(page.locator('summary[aria-label="查看分类名称全文"]')).toHaveCount(0)
        }
        const summary = page.locator('summary[aria-label="查看分类说明全文"]')
        await summary.focus()
        await page.keyboard.press('Enter')
        await expect(page.locator('.overflow-text-full:visible')).toContainText('【说明终点】')
        const full = page.locator('.overflow-text-full:visible')
        expect(await full.evaluate((el) => el.clientHeight)).toBeLessThanOrEqual(180)
        if (count === 30) {
          const wrapper = page.locator('.el-table__body-wrapper .el-scrollbar__wrap')
          expect(await wrapper.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
          await wrapper.evaluate((el) => { el.scrollTop = el.scrollHeight })
        }
        const edit = page.getByRole('button', { name: '编辑', exact: true }).first()
        await edit.click()
        await expect(page.getByRole('dialog', { name: '编辑课程分类' })).toBeVisible()
        await page.keyboard.press('Escape')
        await expect(edit).toBeFocused()
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      if (count === 30) {
        await page.locator('.el-table__body-wrapper .el-scrollbar__wrap').evaluate((el) => { el.scrollTop = 0; el.scrollLeft = 0 })
        await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
        await expect.poll(() => page.evaluate(() => scrollY)).toBe(0)
        await page.screenshot({ path: resolve(`../output/audit-20260913/分类全文布局-${width}.png`), fullPage: true, animations: 'disabled' })
      }
    })
  }
}

test('课程筛选慢响应期间切到旧末页，数据减少后回退而非空页', async ({ page }) => {
  const items = Array.from({ length: 18 }, (_, n) => ({ id: n + 1, name: `课程${n + 1}` }))
  await isolate(page, 'STUDENT', async (url) => {
    if (url.pathname === '/api/courses/categories') return { data: [{ id: 1, name: '计算机' }] }
    if (url.pathname === '/api/courses') {
      if (url.searchParams.has('category_id')) { await pause(800); return { data: items.slice(0, 1) } }
      return { data: items }
    }
  })
  await page.goto('/courses')
  await expect(page.locator('.course-card')).toHaveCount(9)
  await page.locator('.course-filter-field').filter({ hasText: '课程分类' }).locator('.el-select').click()
  await page.getByRole('option', { name: '计算机', exact: true }).click()
  await page.locator('.el-pager li.number').filter({ hasText: /^2$/ }).click()
  await expect(page.locator('.course-card')).toHaveCount(1)
  await expect(page.locator('.course-card')).toContainText('课程1')
  await expect(page.locator('.el-pagination')).toHaveCount(0)
})

test('教师课程长名称键盘全文入口与编辑关闭焦点', async ({ page }) => {
  await isolate(page, 'TEACHER', (url) => url.pathname === '/api/courses/mine' ? { data: [{ id: 1, name: '数据结构与算法课程名称'.repeat(12), status: 'DRAFT', category_id: 1 }] } : null)
  await page.goto('/teacher/courses')
  const summary = page.locator('summary[aria-label="查看课程名称全文"]')
  await summary.focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('.overflow-text-full')).toBeVisible()
  const edit = page.getByRole('button', { name: '编辑', exact: true })
  await edit.click()
  await expect(page.getByRole('dialog', { name: '编辑课程' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(edit).toBeFocused()
})

for (const role of ['STUDENT', 'TEACHER']) {
  test(`${role}测验说明、附件预览关闭后恢复各自入口`, async ({ page }) => {
    const exam = { id: 1, title: '附件测验', exam_type: 'ATTACHMENT', status: 'PUBLISHED', questions: [],
      description: '完整说明'.repeat(100), attachment: 'paper.txt', total_score: 100, availability: 'AVAILABLE' }
    await isolate(page, role, (url) => {
      if (['/api/exams', '/api/exams/manage'].includes(url.pathname)) return { data: [exam] }
      if (url.pathname === '/api/exams/1/attachment') return { raw: '试卷说明' }
    })
    await page.goto('/exams')
    const instructions = page.getByRole('button', { name: '查看完整说明', exact: true })
    await instructions.click()
    await expect(page.getByRole('dialog', { name: '附件测验 · 测验说明' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(instructions).toBeFocused()
    const preview = page.getByRole('button', { name: '测验附件', exact: true })
    await preview.click()
    const dialog = page.getByRole('dialog').filter({ has: page.locator('.attachment-preview') })
    await expect(dialog.locator('iframe')).toBeVisible()
    await dialog.getByRole('button', { name: '关闭', exact: true }).click()
    await expect(preview).toBeFocused()
  })
}

test('答疑保存后原筛选项消失，焦点回到标题而非不存在的回答按钮', async ({ page }) => {
  const item = { id: 1, title: '问题', content: '说明', status: 'WAITING', course_name: '课程', student_name: '学生' }
  await isolate(page, 'TEACHER', (url, request) => {
    if (url.pathname === '/api/questions') return { data: [item] }
    if (request.method() === 'POST') return { data: { ...item, status: 'ANSWERED', answer: { content: '答复' } } }
  })
  await page.goto('/teacher/questions')
  await page.locator('.el-select').click()
  await page.getByRole('option', { name: '等待回答', exact: true }).click()
  await page.getByRole('button', { name: '回答问题', exact: true }).click()
  await page.getByPlaceholder('请输入清晰、准确的回答…').fill('答复')
  await page.getByRole('button', { name: '提交回答', exact: true }).click()
  await expect(page.locator('.teacher-question-card')).toHaveCount(0)
  await expect(page.locator('.page-heading h1')).toBeFocused()
})

test('登录找回密码取消后键盘焦点回到忘记密码', async ({ page }) => {
  await page.goto('/login')
  const opener = page.getByRole('button', { name: '忘记密码', exact: true })
  await opener.click()
  await expect(page.getByRole('dialog', { name: '找回密码' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(opener).toBeFocused()
})

for (const count of [0, 1, 20]) {
  test(`教师公开主页${count}门课程：空状态、单卡与六条分页布局`, async ({ page }) => {
    const courses = Array.from({ length: count }, (_, n) => ({ id: n + 1, name: `授课${n + 1}`, description: '说明' }))
    await isolate(page, 'STUDENT', (url) => url.pathname === '/api/users/2'
      ? { data: { id: 2, role: 'TEACHER', real_name: '教师', created_at: '2026-09-13T00:00:00', courses } } : null)
    await page.setViewportSize({ width: 390, height: 900 })
    await page.goto('/users/2')
    await expect(page.locator('.profile-course-card')).toHaveCount(Math.min(6, count))
    if (!count) await expect(page.getByText('这位教师暂时没有已发布课程', { exact: true })).toBeVisible()
    if (count === 20) {
      const pager = page.locator('.profile-course-section .el-pagination')
      const firstPageY = await pager.evaluate((element) => element.getBoundingClientRect().top + window.scrollY)
      await page.locator('.el-pager li.number').filter({ hasText: /^4$/ }).click()
      await expect(page.locator('.profile-course-card')).toHaveCount(2)
      await expect(page.locator('.profile-course-card').last()).toContainText('授课20')
      const lastPageY = await pager.evaluate((element) => element.getBoundingClientRect().top + window.scrollY)
      expect(Math.abs(lastPageY - firstPageY)).toBeLessThan(1)
      await page.getByRole('listitem', { name: '第 1 页', exact: true }).click()
      await expect(page.locator('.profile-course-card')).toHaveCount(6)
    } else await expect(page.locator('.el-pagination')).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}
