// Isolated browser against the running local demo app; no business mutations.
import { chromium, expect } from '@playwright/test'
import { readFile, mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const report = JSON.parse(await readFile(new URL('../../backend/demo-data-report.json', import.meta.url), 'utf8'))
const baseURL = process.env.DEFENSE_DEMO_URL || 'http://127.0.0.1:5173'
if (!['127.0.0.1', 'localhost', '[::1]'].includes(new URL(baseURL).hostname)) throw new Error('Demo smoke checks only support local hosts')
const screenshots = new URL('../../tmp/demo/', import.meta.url)
await mkdir(screenshots, { recursive: true })
const browser = await chromium.launch()
let pagesChecked = 0
try {
  for (const [account, paths] of [
    ['defense_admin', [['/admin', '系统后台']]],
    ['defense_teacher', [['/classes', '班级管理'], ['/teacher/courses', '教学管理'], ['/teacher/questions', '课程答疑'], ['/homeworks', '作业管理'], ['/exams', '测验管理'], ['/statistics', '教学数据']]],
    ['defense_student01', [['/learning', '我的学习'], ['/classes', '我的班级'], ['/homeworks', '课程作业'], ['/exams', '在线测验'], ['/statistics', '学习数据']]],
    ['defense_student29', [[`/courses/${report.courses.c}`, 'C语言程序设计 · 从入门到实践']]],
  ]) {
    const context = await browser.newContext({ baseURL, viewport: { width: 1440, height: 960 } })
    const page = await context.newPage()
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('response', (response) => {
      if (response.url().includes('/api/') && response.status() >= 400) errors.push(`${response.status()} ${response.url()}`)
    })
    await page.goto('/login')
    await page.getByPlaceholder('用户名、邮箱、学号或工号').fill(account)
    await page.getByPlaceholder('请输入登录密码').fill(process.env.DEFENSE_DEMO_PASSWORD || 'Defense123!')
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page).toHaveURL(baseURL + '/')
    for (const [path, title] of paths) {
      await page.goto(path)
      await expect(page.getByRole('heading', { name: title, exact: true }).first()).toBeVisible()
      await expect(page.locator('.el-loading-mask:visible')).toHaveCount(0)
      if (path === '/statistics') {
        await expect(page.locator('.statistics-chart-canvas svg')).toHaveCount(2)
      }
      if (path === '/learning') {
        const cover = page.locator('.learning-card-mark img').first()
        await expect.poll(() => cover.evaluate((image) => image.naturalWidth)).toBeGreaterThan(0)
        expect(await cover.evaluate((image) => getComputedStyle(image).objectFit)).toBe('contain')
      }
      if (account === 'defense_student29') {
        await expect(page.getByRole('button', { name: '查看课程班级', exact: true })).toHaveText('加入班级')
        const player = page.locator('video')
        await expect.poll(() => player.evaluate((video) => video.readyState)).toBeGreaterThanOrEqual(2)
        await player.evaluate(async (video) => { video.muted = true; await video.play() })
        await expect.poll(() => player.evaluate((video) => video.currentTime)).toBeGreaterThan(0)
        await player.evaluate((video) => video.pause())
      }
      if (account === 'defense_admin') {
        await page.getByText('查看数据图表', { exact: true }).click()
        await expect(page.locator('.statistics-chart-canvas svg')).toHaveCount(2)
        await page.screenshot({ path: fileURLToPath(new URL('defense-admin-charts.png', screenshots)), fullPage: true })
        await page.getByText('查看数据图表', { exact: true }).click()
        await expect(page.locator('.statistics-chart-canvas')).toHaveCount(0)
        await page.getByPlaceholder('搜索视频、课程、教师或文件名').fill('（演示）')
        await page.getByRole('button', { name: '查询任务', exact: true }).click()
        for (const title of ['等待超时任务（演示）', '处理中断任务（演示）']) {
          await expect(page.getByRole('row').filter({ hasText: title })
            .getByRole('button', { name: '重新转码', exact: true })).toBeVisible()
        }
        await page.screenshot({ path: fileURLToPath(new URL('defense-video-processing.png', screenshots)), fullPage: true })
        await page.getByRole('button', { name: /^操作审计/ }).click()
        await expect(page.getByText('准备演示数据', { exact: true })).toBeVisible()
      }
      const widths = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }))
      expect(widths.scroll).toBeLessThanOrEqual(widths.client)
      await page.screenshot({ path: fileURLToPath(new URL(`${account}-${pagesChecked}.png`, screenshots)), fullPage: true })
      pagesChecked += 1
    }
    expect(errors).toEqual([])
    await context.close()
  }
  console.log(JSON.stringify({ demoPagesChecked: pagesChecked, pageErrors: 0 }, null, 2))
} finally {
  await browser.close()
}
