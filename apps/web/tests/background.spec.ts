import { test, expect } from '@playwright/test'

test('all 16 backgrounds re-anchor to wide, square and tall widgets, without clipping or distorting shapes', async ({ page }) => {
  await page.goto('/showcase')
  await page.getByRole('navigation', { name: 'Catalog categories' }).getByRole('button', { name: 'Artwork', exact: true }).click()
  const backgrounds = page.locator('#backgrounds svg.bauhaus-background')
  await expect(backgrounds).toHaveCount(16)
  for (const [width, height] of [[1000, 200], [400, 240], [360, 600], [400, 400]]) {
    await backgrounds.evaluateAll((nodes, size) => nodes.forEach(node => {
      const parent = node.parentElement!
      parent.style.width = `${size.width}px`
      parent.style.height = `${size.height}px`
      parent.style.flex = 'none'
    }), { width, height })
    await expect.poll(async () => backgrounds.evaluateAll(nodes => nodes.every(node => {
      const svg = node as SVGSVGElement, bounds = svg.getBoundingClientRect(), box = svg.viewBox.baseVal
      return Math.abs(bounds.width / bounds.height - box.width / box.height) < .0001
    }))).toBe(true)
    await expect.poll(async () => backgrounds.evaluateAll(nodes => nodes.every(node => {
      const svg = node as SVGSVGElement, bounds = svg.getBoundingClientRect()
      const canvas = svg.querySelector('[data-background-canvas]')!.getBoundingClientRect()
      return Math.abs(canvas.width - bounds.width) < .1 && Math.abs(canvas.height - bounds.height) < .1
    }))).toBe(true)
    const checks = await backgrounds.evaluateAll(nodes => nodes.map(node => {
      const svg = node as SVGSVGElement, bounds = svg.getBoundingClientRect(), canvas = svg.querySelector('[data-background-canvas]')!.getBoundingClientRect()
      const shapes = [...svg.querySelectorAll<SVGGraphicsElement>('path, circle, rect')].filter(shape => !shape.hasAttribute('data-background-canvas'))
      return {
        name: svg.dataset.background,
        canvasFills: Math.abs(canvas.width - bounds.width) < .1 && Math.abs(canvas.height - bounds.height) < .1,
        uniform: shapes.every(shape => { const matrix = shape.getScreenCTM()!; return Math.abs(matrix.a - matrix.d) < .0001 && matrix.b === 0 && matrix.c === 0 }),
        inside: shapes.every(shape => { const rect = shape.getBoundingClientRect(); return rect.left >= bounds.left - .5 && rect.right <= bounds.right + .5 && rect.top >= bounds.top - .5 && rect.bottom <= bounds.bottom + .5 }),
      }
    }))
    for (const check of checks) expect(check, `${check.name} at ${width}×${height}`).toMatchObject({ canvasFills: true, uniform: true, inside: true })
  }
  const inverse = page.locator('#backgrounds [data-background=inverse-poster] [data-background-canvas]')
  await page.evaluate(() => document.documentElement.classList.remove('dark'))
  const light = await inverse.evaluate(node => getComputedStyle(node).fill)
  expect(light).toBe(await page.locator('body').evaluate(node => getComputedStyle(node).backgroundColor))
  await page.evaluate(() => document.documentElement.classList.add('dark'))
  await expect.poll(() => inverse.evaluate(node => getComputedStyle(node).fill)).not.toBe(light)
  const dark = await inverse.evaluate(node => getComputedStyle(node).fill)
  expect(dark).toBe(await page.locator('body').evaluate(node => getComputedStyle(node).backgroundColor))
  expect(dark).not.toBe(light)
})
