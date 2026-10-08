import { randomUUID } from 'node:crypto'
import { test, expect, api, signIn } from './fixtures'
import type { AccountProfile, PublicProfile } from '../src/lib/api'

test('public profile saves handle and bio, renames lookup, and clears bio to null', async ({ page, profile }) => {
  const handle = 'e' + randomUUID().replaceAll('-', '').slice(0, 18)
  await page.goto('/app/profile')
  await page.getByRole('button', { name: 'Edit profile' }).click()
  await page.getByRole('textbox', { name: 'Handle', exact: true }).fill(handle)
  await page.getByRole('textbox', { name: 'Bio', exact: true }).fill('<img src=x onerror=alert(1)> Learning from native data.')
  await page.getByRole('button', { name: 'Save profile', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Edit public profile' })).not.toBeVisible()
  await page.reload()
  await expect(page.getByText('<img src=x onerror=alert(1)> Learning from native data.', { exact: true })).toBeVisible()
  expect(await page.locator('img[src=x]').count()).toBe(0)
  const publicProfile = await api<PublicProfile>(page, `users:lookup?handle=${handle}`, 'GET', undefined, false)
  expect(publicProfile.body.id).toBe(profile.id)
  for (const field of ['settings', 'plan', 'personal_node_id', 'library_node_id', 'activity']) expect(publicProfile.body).not.toHaveProperty(field)
  await page.goto(`/u/${handle}`)
  await page.getByRole('button', { name: 'Edit profile' }).click()
  await page.getByRole('textbox', { name: 'Handle', exact: true }).fill(handle + 'x')
  await page.getByRole('textbox', { name: 'Bio', exact: true }).fill('')
  await page.getByRole('button', { name: 'Save profile', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`/u/${handle}x$`))
  expect((await api(page, `users:lookup?handle=${handle}`, 'GET', undefined, false)).status).toBe(404)
  expect((await api<AccountProfile>(page, 'me')).body).toMatchObject({ id: profile.id, bio: null, handle: handle + 'x' })
})

test('duplicate and invalid handles preserve saved profile and editable draft', async ({ page, browser, baseURL, profile }) => {
  const context = await browser.newContext({ baseURL })
  try {
    const other = await context.newPage()
    await signIn(other, 'B')
    const handle = 'e' + randomUUID().replaceAll('-', '').slice(0, 18)
    expect((await api(other, 'me/profile', 'PATCH', { handle })).status).toBe(200)
    await page.goto('/app/profile')
    await page.getByRole('button', { name: 'Edit profile' }).click()
    await page.getByRole('textbox', { name: 'Handle', exact: true }).fill('1 invalid')
    await expect(page.getByRole('button', { name: 'Save profile', exact: true })).toBeDisabled()
    expect((await api(page, 'me/profile', 'PATCH', { handle: '1 invalid', bio: 'must not persist' })).status).toBe(422)
    await page.getByRole('textbox', { name: 'Handle', exact: true }).fill(handle)
    await page.getByRole('textbox', { name: 'Bio', exact: true }).fill('keep this draft')
    await page.getByRole('button', { name: 'Save profile', exact: true }).click()
    await expect(page.getByText('This handle is already taken. Choose another handle.')).toBeVisible()
    await expect(page.getByRole('textbox', { name: 'Bio', exact: true })).toHaveValue('keep this draft')
    expect((await api<AccountProfile>(page, 'me')).body).toMatchObject({ handle: profile.handle, bio: profile.bio })
  } finally { await context.close() }
})

test('settings persist languages and timezone, reject invalid drafts, and survive another session', async ({ page, browser, baseURL, profile }) => {
  try {
    await page.goto('/app/settings')
    await page.getByRole('combobox', { name: /^Time zone/ }).fill('not/a/timezone')
    await expect(page.getByRole('button', { name: 'Save changes', exact: true })).toBeDisabled()
    await page.getByRole('combobox', { name: /^Time zone/ }).fill('Asia/Ho_Chi_Minh')
    await page.getByLabel(/Interface language/).selectOption('vi')
    await page.getByLabel(/Translation language/).selectOption('en')
    const saved = page.waitForResponse(r => r.url().endsWith('/me/settings') && r.request().method() === 'PATCH')
    await page.getByRole('button', { name: 'Save changes', exact: true }).click()
    expect((await saved).status()).toBe(200)
    await page.reload()
    await expect(page.getByRole('combobox', { name: /^Time zone/ })).toHaveValue('Asia/Ho_Chi_Minh')
    const context = await browser.newContext({ baseURL })
    try {
      const other = await context.newPage()
      await signIn(other)
      await other.goto('/app/settings')
      await expect(other.getByRole('combobox', { name: /^Time zone/ })).toHaveValue('Asia/Ho_Chi_Minh')
      expect((await api<AccountProfile>(other, 'me')).body.settings).toMatchObject({ timezone: 'Asia/Ho_Chi_Minh', locale: 'vi', translation_language: 'en' })
    } finally { await context.close() }
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})

test('Free and Pro learning options enforce backend entitlement and keep failed drafts', async ({ page, browser, baseURL, profile }) => {
  expect(profile.plan.toUpperCase()).toBe('FREE')
  await page.goto('/app/settings')
  await page.getByRole('button', { name: 'Learning', exact: true }).click()
  await expect(page.getByRole('checkbox', { name: /Single word/ })).toBeDisabled()
  expect((await api(page, 'me/settings', 'PATCH', { learning: { formats: ['SINGLE_WORD'] } })).status).toBe(403)
  await page.getByLabel(/Questions per sense/).fill('2')
  await page.route('**/api/v1/me/settings', route => route.abort('connectionfailed'))
  await page.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(page.getByText(/Could not|fetch/i).first()).toBeVisible()
  await expect(page.getByLabel(/Questions per sense/)).toHaveValue('2')
  await page.unroute('**/api/v1/me/settings')
  await page.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(page.getByText('Settings saved', { exact: true })).toBeVisible()
  expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200)
  const context = await browser.newContext({ baseURL })
  try {
    const other = await context.newPage()
    expect((await signIn(other, 'B')).plan.toUpperCase()).toBe('PRO')
    await other.goto('/app/settings')
    await other.getByRole('button', { name: 'Learning', exact: true }).click()
    await expect(other.getByRole('checkbox', { name: /Single word/ })).toBeEnabled()
  } finally { await context.close() }
})
