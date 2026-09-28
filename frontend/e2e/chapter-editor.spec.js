import { expect, test } from '@playwright/test'
import { resolve } from 'node:path'

const pause = (ms) => new Promise((done) => setTimeout(done, ms))
async function isolate(page, course, handler = () => null) {
  await page.addInitScript(() => localStorage.setItem('access_token', 'isolated-chapter'))
  await page.route(/https?:\/\/[^/]+\/api\//, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const result = await handler(url, request) || {}
    const defaults = url.pathname === '/api/users/me' ? { id: 1, role: 'TEACHER', real_name: '测试教师' }
      : url.pathname === '/api/courses/mine' ? [course]
        : url.pathname.includes('/notifications') ? { items: [], unread_count: 0, pagination: {} } : []
    await route.fulfill({ status: result.status || 200, contentType: 'application/json', body: JSON.stringify({ code: result.status || 200, data: result.data ?? defaults, message: result.message }) })
  })
}
function fixture(count = 1, status = 'DRAFT') {
  return { id: 1, name: '课程一', status, chapters: [
    { id: 11, title: '章节一', description: '说明一', sort_order: 0, videos: Array.from({ length: count }, (_, n) => ({ id: n + 21, title: `${'视频标题'.repeat(12)}-${n + 1}`, status: 'READY', sort_order: n })) },
    { id: 12, title: '章节二', videos: [{ id: 80, title: '仅属于第二章的视频', status: 'READY' }] },
  ] }
}
async function openChapter(page) {
  await page.goto('/teacher/courses')
  await page.getByRole('button', { name: '展开当前行' }).click()
  await page.locator('.chapter-row').filter({ hasText: '章节一' }).getByRole('button', { name: '编辑', exact: true }).click()
  return page.getByRole('dialog', { name: '编辑章节' })
}

for (const [width, count] of [[390, 0], [1440, 1], [390, 20], [1440, 20]]) {
  test(`章节资料与${count}个所属视频在同一固定弹窗内-${width}`, async ({ page }) => {
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.setViewportSize({ width, height: 900 })
    await isolate(page, fixture(count))
    const dialog = await openChapter(page)
    await expect(dialog.locator('.chapter-editor-video')).toHaveCount(count)
    await expect(dialog).not.toContainText('仅属于第二章的视频')
    if (count) {
      await dialog.getByRole('button', { name: '编辑视频', exact: true }).first().click()
      await expect(page.locator('.el-dialog:visible')).toHaveCount(1)
      await expect(dialog.getByPlaceholder('请输入视频标题')).toBeVisible()
      await expect(dialog.getByPlaceholder('请输入视频标题')).toBeFocused()
      await expect(dialog.getByPlaceholder('例如：第一章 课程导学')).toBeVisible()
      await dialog.getByRole('button', { name: '取消视频编辑' }).click()
      await expect(dialog.getByRole('button', { name: '编辑视频', exact: true }).first()).toBeFocused()
    } else await expect(dialog.getByText('本章节还没有视频', { exact: true })).toBeVisible()
    await dialog.getByRole('button', { name: '上传视频', exact: true }).click()
    await expect(page.locator('.el-dialog:visible')).toHaveCount(1)
    await expect(dialog.getByRole('button', { name: '上传并处理' })).toBeVisible()
    await expect(dialog.getByPlaceholder('请输入视频标题')).toBeFocused()
    if (count === 20) expect(await dialog.locator('.chapter-editor-videos').evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
    const box = await page.locator('.el-dialog:visible').boundingBox()
    expect(box.width).toBeLessThanOrEqual(width - 32)
    expect(box.y).toBeGreaterThanOrEqual(16)
    expect(box.y + box.height).toBeLessThanOrEqual(884)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: resolve(`../output/audit-20260913/章节视频统一弹窗-${width}-${count}.png`), animations: 'disabled' })
    expect(errors).toEqual([])
  })
}

test('视频保存留在章节弹窗，刷新视频不覆盖章节草稿，慢请求锁定关闭和重复操作', async ({ page }) => {
  const course = fixture()
  let writes = 0
  let chapterPayload
  await isolate(page, course, async (url, request) => {
    if (url.pathname === '/api/videos/21' && request.method() === 'PUT') {
      writes += 1
      await pause(500)
      Object.assign(course.chapters[0].videos[0], request.postDataJSON())
      return { data: course.chapters[0].videos[0] }
    }
    if (url.pathname === '/api/courses/1/chapters/11' && request.method() === 'PUT') {
      chapterPayload = request.postDataJSON()
      Object.assign(course.chapters[0], chapterPayload)
      return { data: course.chapters[0] }
    }
  })
  const dialog = await openChapter(page)
  await dialog.getByPlaceholder('例如：第一章 课程导学').fill('尚未保存的章节标题')
  await dialog.getByRole('button', { name: '编辑视频', exact: true }).click()
  await dialog.getByPlaceholder('请输入视频标题').fill('已修改的视频')
  await dialog.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(dialog.getByRole('button', { name: '关闭', exact: true })).toBeDisabled()
  await expect(dialog.getByRole('button', { name: '取消视频编辑' })).toBeDisabled()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeVisible()
  await expect(dialog.locator('.chapter-video-form')).toHaveCount(0)
  await expect(dialog.getByPlaceholder('例如：第一章 课程导学')).toHaveValue('尚未保存的章节标题')
  await expect(dialog.locator('.chapter-editor-video')).toContainText('已修改的视频')
  expect(writes).toBe(1)
  await dialog.getByRole('button', { name: '保存章节', exact: true }).click()
  await expect(page.getByText('章节信息已更新')).toBeVisible()
  expect(chapterPayload.title).toBe('尚未保存的章节标题')
  await expect(dialog).toBeVisible()
})

test('新增章节先保存再上传，重存不重复创建，视频上传使用当前章节编号', async ({ page }) => {
  const course = fixture(0)
  let creates = 0
  let uploadedBody = ''
  await isolate(page, course, (url, request) => {
    if (url.pathname === '/api/courses/1/chapters' && request.method() === 'POST') {
      creates += 1
      const chapter = { id: 13, ...request.postDataJSON(), videos: [] }
      course.chapters.push(chapter)
      return { data: chapter }
    }
    if (url.pathname === '/api/courses/1/chapters/13') return { data: course.chapters[2] }
    if (url.pathname === '/api/videos/upload') { uploadedBody = request.postData(); return { data: { id: 90, status: 'READY' } } }
  })
  await page.goto('/teacher/courses')
  await page.getByRole('button', { name: '添加章节', exact: true }).click()
  let dialog = page.getByRole('dialog', { name: '添加章节' })
  await expect(dialog.getByRole('button', { name: '上传视频', exact: true })).toBeDisabled()
  await dialog.getByPlaceholder('例如：第一章 课程导学').fill('新章节')
  await dialog.getByRole('button', { name: '保存章节', exact: true }).click()
  dialog = page.getByRole('dialog', { name: '编辑章节' })
  await expect(dialog.getByRole('button', { name: '上传视频', exact: true })).toBeEnabled()
  await dialog.getByRole('button', { name: '保存章节', exact: true }).click()
  await expect(page.getByText('章节信息已更新')).toBeVisible()
  expect(creates).toBe(1)
  await dialog.getByRole('button', { name: '上传视频', exact: true }).click()
  await dialog.getByPlaceholder('请输入视频标题').fill('新章节视频')
  await dialog.locator('input[type="file"]').setInputFiles({ name: 'sample.mp4', mimeType: 'video/mp4', buffer: Buffer.from('isolated fixture') })
  await dialog.getByRole('button', { name: '上传并处理', exact: true }).click()
  await expect(dialog.locator('.chapter-video-form')).toHaveCount(0)
  expect(uploadedBody).toMatch(/name="chapter_id"\r\n\r\n13/)
})

test('已发布章节允许视频资料编辑但不替换删除，保存失败保留两个草稿', async ({ page }) => {
  await isolate(page, fixture(1, 'PUBLISHED'), (url, request) => request.method() === 'PUT' ? { status: 500, message: '测试保存失败' } : null)
  const dialog = await openChapter(page)
  await expect(dialog.getByRole('button', { name: '替换文件' })).toHaveCount(0)
  await expect(dialog.getByRole('button', { name: '删除视频' })).toHaveCount(0)
  await dialog.getByPlaceholder('例如：第一章 课程导学').fill('章节草稿')
  await dialog.getByRole('button', { name: '编辑视频', exact: true }).click()
  await dialog.getByPlaceholder('请输入视频标题').fill('视频草稿')
  await dialog.getByRole('button', { name: '保存修改', exact: true }).click()
  await expect(page.getByText('测试保存失败')).toBeVisible()
  await expect(dialog.getByPlaceholder('例如：第一章 课程导学')).toHaveValue('章节草稿')
  await expect(dialog.getByPlaceholder('请输入视频标题')).toHaveValue('视频草稿')
  await expect(dialog.getByRole('button', { name: '关闭', exact: true })).toBeEnabled()
})
