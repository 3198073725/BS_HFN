import { expect } from '@playwright/test'

// Measure the actual box, never the full-screen overlay with role="dialog".
export async function expectCompactMessageBox(page, box = page.locator('.el-message-box'), { long = false, width = 420 } = {}) {
  await expect(box).toBeVisible()
  const viewport = page.viewportSize()
  await expect.poll(async () => {
    const rect = await box.boundingBox()
    return Math.max(
      Math.abs(rect.width - Math.min(width, viewport.width - 32)),
      Math.abs(rect.x + rect.width / 2 - viewport.width / 2),
      Math.abs(rect.y + rect.height / 2 - viewport.height / 2),
    )
  }).toBeLessThanOrEqual(1)
  const rect = await box.boundingBox()
  expect(rect.x).toBeGreaterThanOrEqual(15)
  expect(rect.y).toBeGreaterThanOrEqual(15)
  expect(rect.y + rect.height).toBeLessThanOrEqual(viewport.height - 15)
  if (!long) expect(rect.height).toBeLessThanOrEqual(240)
  expect(await box.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
  for (const button of await box.locator('.el-message-box__btns button').all()) {
    await expect(button).toBeInViewport({ ratio: 1 })
  }
}
