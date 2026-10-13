import { test, expect } from '@playwright/test'
import { buildFixture, renderFixture } from './fixtures/render-fixture'
import messages from '../../../src/messages/vi.json' with { type: 'json' }

test('denied clipboard offers the exact selectable pattern and localized descriptions', async ({ page }) => {
  const bundle = await buildFixture('pattern')
  await renderFixture(page, bundle, 'pattern')
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: async () => { throw new Error('denied') } } })
  })
  const pattern = "bank {one's} {clause}"
  await expect(page.getByTitle(messages.dictionary.slotPossessive, { exact: true })).toBeVisible()
  await page.getByRole('button', { name: messages.dictionary.grammarPattern.replace('{pattern}', pattern) }).click()
  await expect(page.getByText(messages.dictionary.patternCopyFailed, { exact: true })).toBeVisible()
  const fallback = page.getByRole('textbox')
  await expect(fallback).toHaveValue(pattern)
  await fallback.focus()
  expect(await fallback.evaluate(input => (input as HTMLInputElement).selectionEnd)).toBe(pattern.length)
})
