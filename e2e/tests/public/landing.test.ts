import { test, expect } from '../../fixtures/index.ts'

test('guest can reach sign-in and sign-up from the public landing', async ({ page }) => {
  const accountReads: string[] = []
  page.on('request', request => { if (request.url().includes('/v1/me')) accountReads.push(request.url()) })
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  const navigation = page.getByRole('navigation', { name: 'Main navigation' })
  await expect(navigation.getByRole('link', { name: 'Get started' })).toHaveAttribute('href', '/signup')
  await navigation.getByRole('link', { name: 'Sign in', exact: true }).click()
  await expect(page.getByLabel('Email', { exact: true })).toBeVisible()
  expect(accountReads).toEqual([])
})
