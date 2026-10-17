import { expect, test } from '@playwright/test'
import { preparation } from '../../unit/fixtures'
import { accountPlatform, navigationPlatform } from './fixtures/api-fixtures'
import { buildFixture, renderFixture } from './fixtures/render-fixture'

test('study waits for native job completion after HTTP acceptance', async ({ page }) => {
  const bundle = await buildFixture('study', { '@/features/account/account.client': accountPlatform, 'next/navigation': navigationPlatform })
  // This contract fixture needs no live Next.js route or stylesheet.
  await page.route('**/app', route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body></body></html>' }))
  const id = '01900000-0000-7000-8000-000000000001'
  let polls = 0
  let submissions = 0
  await page.route('**/*v1/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/words:batchPreview')) return route.fulfill({ json: [{ word_id: 1, lemma: 'bank', entry_type: 'word', senses: [preparation(1, 'single_word').bundles[0].sense] }] })
    expect(route.request().headers().authorization).toBe('Bearer test-only-bearer')
    if (path.endsWith('/study:prepare')) {
      submissions++
      return route.fulfill({ status: 202, headers: { Location: `/v1/jobs/${id}`, 'Retry-After': '2' }, json: { job_id: id, status_url: `/v1/jobs/${id}` } })
    }
    expect(path.endsWith(`/jobs/${id}`)).toBe(true)
    polls++
    return route.fulfill({ headers: { 'Retry-After': '2' }, json: { job_id: id, status: polls < 3 ? 'running' : 'succeeded', result: polls < 3 ? null : preparation(1, 'single_word'), error: null } })
  })
  await renderFixture(page, bundle, 'study', '?node=deck&selection=new')
  await expect.poll(() => polls).toBeGreaterThan(0)
  await expect(page.getByRole('textbox', { name: 'Your word' })).toHaveCount(0)
  await expect(page.getByRole('textbox', { name: 'Your word' })).toBeVisible({ timeout: 10_000 })
  expect(submissions).toBe(1)
  expect(polls).toBe(3)
})

test('word picker reads the completed word by ID before search catches up', async ({ page }) => {
  const bundle = await buildFixture('word-picker')
  await page.route('**/app', route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body></body></html>' }))
  const id = '01900000-0000-7000-8000-000000000002'
  let previews = 0
  await page.route('**/*v1/**', route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/words:search')) return route.fulfill({ json: { items: [{ kind: 'reference', reference_id: 'entry_example', display: 'bank', entry_type: 'word', match_kind: 'exact', matched_surface: 'bank' }] } })
    if (path.endsWith('/words:generate')) return route.fulfill({ status: 202, json: { job_id: id, status_url: `/v1/jobs/${id}` } })
    if (path.endsWith(`/jobs/${id}`)) return route.fulfill({ json: { job_id: id, status: 'succeeded', result: { word_id: 1 }, error: null } })
    expect(path.endsWith('/words:batchPreview')).toBe(true)
    expect(route.request().postDataJSON()).toEqual({ word_ids: [1] })
    previews++
    return route.fulfill({ json: [{ word_id: 1, lemma: 'bank', entry_type: 'word', senses: [preparation().bundles[0].sense] }] })
  })
  await renderFixture(page, bundle, 'word-picker')
  const picker = page.getByRole('dialog', { name: 'Add words to deck' })
  await picker.getByRole('searchbox', { name: 'Search words' }).fill('bank')
  await picker.getByRole('button', { name: 'Prepare entry' }).click()
  await expect(picker.getByRole('checkbox').first()).toBeVisible()
  expect(previews).toBe(1)
})
