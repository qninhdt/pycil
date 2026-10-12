import { randomUUID } from 'node:crypto'
import { api } from './helpers/api'
import { signIn } from './helpers/auth'

import { expect,test } from './fixtures'

import type { AccountProfile,PublicProfile } from '../../src/lib/api'

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
    await expect(page.getByText('That handle is already taken. Choose another one.')).toBeVisible()
    await expect(page.getByRole('textbox', { name: 'Bio', exact: true })).toHaveValue('keep this draft')
    expect((await api<AccountProfile>(page, 'me')).body).toMatchObject({ handle: profile.handle, bio: profile.bio })
  } finally { await context.close() }
})

test('delayed Clerk hydration cannot expose an editable profile that disappears during session loading', async ({ page, profile }) => {
  let release!: () => void, reached!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const requested = new Promise<void>(resolve => { reached = resolve })
  await page.route('**/npm/@clerk/clerk-js@*/dist/clerk.browser.js*', async route => {
    reached()
    await gate
    await route.continue()
  }, { times: 1 })
  try {
    await page.goto(`/u/${profile.id}`, { waitUntil: 'commit' })
    await requested
    await expect(page.getByRole('button', { name: 'Edit profile', exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Open PycilAI', exact: true })).toBeDisabled()
    release()
    await expect(page.getByRole('button', { name: 'Edit profile', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Edit profile', exact: true }).click()
    const form = page.getByRole('dialog', { name: 'Edit public profile' })
    await form.getByRole('textbox', { name: 'Bio', exact: true }).fill('draft survives hydration')
    await expect(form.getByRole('textbox', { name: 'Bio', exact: true })).toHaveValue('draft survives hydration')
    await expect(form).toBeVisible()
  } finally { release() }
})
