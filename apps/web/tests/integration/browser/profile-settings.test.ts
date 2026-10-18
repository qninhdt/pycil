import { expect,test } from '@playwright/test'
import { accountPlatform,navigationPlatform } from './fixtures/api-fixtures'
import { buildFixture,renderFixture } from './fixtures/render-fixture'


test('public profiles use /u and expose only published material', async ({ page }) => {
  await page.goto('/u/sam')
  await page.getByRole('button', { name: 'Open account menu' }).click()
  await page.getByRole('menuitem', { name: 'Sign out' }).click()
  await expect(page.getByRole('heading', { name: 'Sam' })).toBeVisible()
  await expect(page.getByRole('link', { name: /Travel essentials/ })).toBeVisible()
  await expect(page.getByText('Current streak')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Edit profile' })).toHaveCount(0)
  await page.getByRole('link', { name: /Travel essentials/ }).click()
  await expect(page).toHaveURL(/\/u\/sam\/travel-source$/)
  await expect(page.getByRole('heading', { name: 'Travel essentials' })).toBeVisible()
  await expect(page.getByText('Due', { exact: true })).toHaveCount(0)
})

test('own profile opens edit modal, adapts to mobile and validates inputs', async ({ page }) => {
  await page.goto('/u/preview-alex')
  await expect(page).toHaveURL(/\/u\/preview-alex$/)
  await page.getByRole('button', { name: 'Edit profile' }).click()
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('textbox', { name: 'Display name' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.getByRole('textbox', { name: 'Display name' }).fill(' ')
  await expect(page.getByRole('button', { name: 'Save profile' })).toBeDisabled()
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Alex' })).toBeVisible()
})

test('settings show all three response formats and persist supported choices', async ({ page }) => {
  await page.goto('/app/settings')
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
  await page.getByRole('button', { name: 'Learning' }).click()
  expect(await page.locator('[data-learning-icon]').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-learning-icon')))).toEqual([
    'definition_to_word', 'word_to_definition', 'context_to_word', 'cloze_to_word', 'dialogue_completion', 'word_to_usage', 'meaning_in_context', 'sentence_rewrite',
    'single_choice', 'single_word', 'short_answer',
  ])
  await page.evaluate(() => document.documentElement.classList.add('dark'))
  await page.evaluate(() => document.documentElement.classList.remove('dark'))
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await expect(page.getByText('Multiple choice', { exact: true })).toBeVisible()
  await expect(page.getByText('Single word', { exact: true })).toBeVisible()
  await expect(page.getByText('Short answer', { exact: true })).toBeVisible()
  await expect(page.getByRole('checkbox', { name: /Single word/ })).toBeChecked()
  await expect(page.getByRole('checkbox', { name: /Short answer/ })).toBeChecked()
  await expect(page.getByRole('checkbox', { name: /Single word/ })).toBeEnabled()
  await expect(page.getByRole('checkbox', { name: /Short answer/ })).toBeEnabled()
  await page.getByRole('spinbutton', { name: /Questions per sense/ }).fill('4')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByRole('button', { name: 'Save changes' })).toBeDisabled()
  await page.getByRole('button', { name: 'General' }).click()
  await page.getByRole('button', { name: 'Learning' }).click()
  await expect(page.getByRole('spinbutton', { name: /Questions per sense/ })).toHaveValue('4')
})

test('HTTP settings keep the draft after a rejected save and send only the changed native fields', async ({ page }) => {
  const bundle = await buildFixture('account', { '@/features/account/account.client': accountPlatform, 'next/navigation': navigationPlatform })
  const patches: unknown[] = []
  await page.route('**/*v1/**', route => {
    expect(new URL(route.request().url()).pathname.endsWith('/me/settings')).toBe(true)
    expect(route.request().method()).toBe('PATCH')
    expect(route.request().headers().authorization).toBe('Bearer test-only-bearer')
    patches.push(route.request().postDataJSON())
    return route.fulfill({ status: 503, json: { error: 'settings_unavailable' } })
  })
  await renderFixture(page, bundle, 'account', '?settings')
  await page.getByRole('button', { name: 'Learning', exact: true }).click()
  const count = page.getByLabel(/^Questions per sense/)
  await count.fill('1')
  const rejected = page.waitForResponse(response => response.url().endsWith('/me/settings'))
  await page.getByRole('button', { name: 'Save changes', exact: true }).click()
  expect((await rejected).status()).toBe(503)
  await expect(page.getByRole('button', { name: 'Save changes', exact: true })).toBeEnabled()
  await expect(count).toHaveValue('1')
  expect(patches).toEqual([{ learning: { questions_per_sense: 1 } }])
})
