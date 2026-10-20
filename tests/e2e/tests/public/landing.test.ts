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

test('signed-in visitors can open the landing account menu', async ({ user }) => {
  await user.page.goto('/')
  const navigation = user.page.getByRole('navigation', { name: 'Main navigation' })
  await expect(navigation.getByRole('link', { name: 'Open the app', exact: true })).toBeVisible()
  const account = navigation.getByRole('button', { name: 'Open user menu', exact: true })
  await expect(account).toBeVisible()
  await account.click()
  await expect(user.page.getByRole('button', { name: 'Manage account', exact: true })).toBeVisible()
})
