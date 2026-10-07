import { expect, test } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import database from '../src/lib/services/mock/database.json' with { type: 'json' }
import { createMockServices } from '../src/lib/services/mock'

test('public account contract omits private settings and supports bio before a handle', async () => {
  const fixture = structuredClone(database)
  Object.assign(fixture.account, { handle: null })
  const services = createMockServices({ database: fixture, latency: 0 })
  const signal = new AbortController().signal
  expect(await services.account.publicProfile('preview-alex', signal)).not.toHaveProperty('settings')
  await expect(services.library.publicContents('preview-personal', undefined, signal)).rejects.toMatchObject({ status: 404 })
  const edited = await services.account.updateProfile({ bio: 'A public introduction.' }, signal)
  expect(edited.handle).toBeNull()
  expect((await services.account.publicProfile('preview-alex', signal)).bio).toBe('A public introduction.')
})

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

test('own profile routes to the public address and edits public fields', async ({ page }) => {
  await page.goto('/app/profile')
  await expect(page).toHaveURL(/\/u\/preview-alex$/)
  await page.getByRole('button', { name: 'Edit profile' }).click()
  await page.getByRole('textbox', { name: 'Bio' }).fill('Learning one meaning at a time.')
  await page.getByRole('button', { name: 'Save profile' }).click()
  await expect(page.getByText('Learning one meaning at a time.')).toBeVisible()
})

test('settings show all three response formats and persist supported choices', async ({ page }) => {
  await page.goto('/app/settings')
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
  await page.getByRole('button', { name: 'Learning' }).click()
  expect(await page.locator('[data-learning-icon]').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-learning-icon')))).toEqual([
    'DEFINITION_TO_WORD', 'WORD_TO_DEFINITION', 'CONTEXT_TO_WORD', 'CLOZE_TO_WORD', 'DIALOGUE_COMPLETION', 'WORD_TO_USAGE', 'MEANING_IN_CONTEXT',
    'SINGLE_CHOICE', 'SINGLE_WORD', 'SHORT_ANSWER',
  ])
  mkdirSync('../../.impeccable/review', { recursive: true })
  await page.screenshot({ path: '../../.impeccable/review/settings-learning-icons.png', fullPage: true })
  await page.evaluate(() => document.documentElement.classList.add('dark'))
  await page.screenshot({ path: '../../.impeccable/review/settings-learning-icons-dark.png', fullPage: true })
  await page.evaluate(() => document.documentElement.classList.remove('dark'))
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: '../../.impeccable/review/settings-learning-icons-mobile.png', fullPage: true })
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
