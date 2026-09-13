import { expect, test } from '@playwright/test'
import { expectCompactMessageBox } from './message-box-layout'

for (const viewport of [{ width: 2048, height: 950 }, { width: 390, height: 844 }]) {
  test(`确认、输入和警告框保持合理尺寸及内容滚动 ${viewport.width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport)
    await page.goto('/e2e/fixtures/message-box.html')
    await expect(page.locator('body')).toHaveAttribute('data-ready', 'true')
    const box = page.locator('.el-message-box')
    for (const id of ['confirm', 'prompt', 'neutral', 'custom']) {
      await page.locator(`#${id}`).click()
      await expectCompactMessageBox(page, box, { width: id === 'custom' ? 480 : 420 })
      if (id === 'prompt') await box.getByPlaceholder('说明内容').fill('测试输入')
      if (id === 'confirm') await page.screenshot({ path: testInfo.outputPath('compact-confirmation.png') })
      await box.getByRole('button', { name: '取消', exact: true }).click()
      await expect(box).toBeHidden()
    }
    await page.locator('#long').click()
    await expectCompactMessageBox(page, box, { long: true })
    const content = box.locator('.el-message-box__content')
    expect(await content.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true)
    const before = await box.boundingBox()
    await content.evaluate((element) => { element.scrollTop = element.scrollHeight })
    expect(await content.evaluate((element) => element.scrollTop)).toBeGreaterThan(0)
    const after = await box.boundingBox()
    expect(Math.abs(after.y - before.y)).toBeLessThanOrEqual(1)
    await expectCompactMessageBox(page, box, { long: true })
    await page.screenshot({ path: testInfo.outputPath('scrolling-warning.png') })
    await box.getByRole('button', { name: '确定', exact: true }).click()
    await expect(box).toBeHidden()
  })
}
