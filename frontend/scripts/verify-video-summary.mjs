// 使用模拟接口验证切换视频不会串用总结，也不会触发课程批量任务。
import assert from 'node:assert/strict'
import { chromium } from '@playwright/test'

const browser = await chromium.launch({ headless: true })
try {
  const page = await browser.newPage()
  page.on('pageerror', (error) => console.error('页面异常：', error.message))
  await page.addInitScript(() => localStorage.setItem('access_token', 'ui-test-token'))
  const generated = []
  let firstQueued = false
  let studentView = false
  const summaryMarkdown = [
    '## 视频总结', '', '### 核心知识', '', '- **变量**与类型', '- 循环', '',
    '1. 理解', '2. 练习', '', '> 学习建议', '',
    '| 名称 | 说明 |', '| --- | --- |', '| int | 整数 |', '',
    '```c', 'int main(void) { return 0; }', '```', '',
    '<script>window.__summaryXss = 1</script>', '[危险链接](javascript:alert(1))',
  ].join('\n')
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    let data = {}
    if (path === '/api/users/me') data = { id: studentView ? 8 : 7, role: studentView ? 'STUDENT' : 'TEACHER', real_name: '测试用户' }
    else if (path === '/api/courses/4/classes') data = []
    else if (path === '/api/learning/courses/4/state') data = { joined: false, favorited: false }
    else if (path === '/api/courses/4') data = {
      id: 4, name: '测试课程', status: 'PUBLISHED', teacher_id: 7, teacher_name: '测试教师',
      chapters: [{ id: 1, title: '测试章节', videos: [
        { id: 101, title: '视频一', status: 'READY', hls_url: '/test-one.m3u8' },
        { id: 102, title: '视频二', status: 'READY', hls_url: '/test-two.m3u8' },
      ] }],
    }
    else if (path.endsWith('/ai-summary/generate')) {
      generated.push(path)
      firstQueued = true
      data = { status: 'QUEUED' }
    } else if (path === '/api/videos/101/ai-summary') data = {
      video_id: 101, video_title: '视频一', manager: !studentView, unlocked: true, configured: true,
      status: studentView ? 'PUBLISHED' : firstQueued ? 'SUBTITLING' : 'NOT_GENERATED',
      content: studentView ? summaryMarkdown : null, progress: 25, progress_message: '已识别至 01:00',
    }
    else if (path === '/api/videos/102/ai-summary') data = {
      video_id: 102, video_title: '视频二', manager: true, unlocked: true, configured: true,
      status: 'DRAFT', content: '视频二专属总结', progress: 100,
    }
    else if (path.endsWith('/subtitle')) return route.fulfill({ status: 404, json: { code: 404, message: '暂无字幕' } })
    await route.fulfill({ json: { code: 200, data, message: '成功' } })
  })
  await page.goto(process.env.VERIFY_WEB_URL || 'http://127.0.0.1:5173/courses/4')
  const panel = page.getByRole('region', { name: '当前视频 AI 总结' })
  try {
    await panel.getByText('当前视频：视频一', { exact: true }).waitFor({ timeout: 10000 })
  } catch (error) {
    console.error((await page.locator('body').innerText()).slice(0, 3500))
    throw error
  }
  await panel.getByRole('button', { name: '生成当前视频字幕及总结' }).click()
  await page.getByRole('button', { name: '确定', exact: true }).click()
  await panel.getByText('已识别至 01:00', { exact: true }).waitFor()
  await page.locator('.video-list button').filter({ hasText: '视频二' }).click()
  await panel.getByText('当前视频：视频二', { exact: true }).waitFor()
  assert.equal(await panel.getByRole('textbox', { name: '编辑当前视频总结' }).inputValue(), '视频二专属总结')
  assert.deepEqual(generated, ['/api/videos/101/ai-summary/generate'])
  assert.equal(await panel.getByText('已识别至 01:00', { exact: true }).count(), 0)
  console.log('通过：只生成视频一，切换视频二后展示其独立总结，无课程批量请求。')
  studentView = true
  await page.reload()
  const markdown = panel.locator('.markdown-content')
  await markdown.getByRole('heading', { name: '视频总结', exact: true }).waitFor()
  assert.equal(await markdown.locator('strong').innerText(), '变量')
  assert.equal(await markdown.locator('ul li').count(), 2)
  assert.equal(await markdown.locator('ol li').count(), 2)
  assert.equal(await markdown.locator('table').count(), 1)
  assert.equal(await markdown.locator('pre code').innerText(), 'int main(void) { return 0; }\n')
  assert.equal(await markdown.locator('script, a[href^="javascript:"]').count(), 0)
  assert.equal(await page.evaluate(() => window.__summaryXss || 0), 0)
  await page.setViewportSize({ width: 390, height: 844 })
  assert.ok(await markdown.evaluate((element) => element.getBoundingClientRect().right <= window.innerWidth))
  console.log('通过：学生端已发布总结正确显示 Markdown 标题、列表、表格和代码块，手机端内容框无溢出。')
} finally {
  await browser.close()
}
