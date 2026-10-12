import { appendFileSync } from 'node:fs'
import { parseAccountProfile } from '../../src/lib/api'
import { api } from './helpers/api'
import { signIn,signOut,verifyDevice } from './helpers/auth'

import { createHmac,randomUUID } from 'node:crypto'

import { setupClerkTestingToken } from '@clerk/testing/playwright'

import { expect,test } from './fixtures'

import type { AccountProfile } from '../../src/lib/api'

import type { StudyActivity,StudySummary } from '../../src/lib/home-api'

import type { Conversation } from '../../src/lib/assistant-api'

import { session,start } from './helpers/study'

async function signup(page: import('@playwright/test').Page, destination = '/app') {
  const email = `pycil-${process.env.E2E_RUN_ID}-${randomUUID().slice(0, 8)}+clerk_test@example.com`
  const password = randomUUID() + 'Aa1!'
  if (!process.env.E2E_ACCOUNT_LEDGER) throw new Error('Signup tests require the managed runner and its owned-user ledger.')
  appendFileSync(process.env.E2E_ACCOUNT_LEDGER, email + '\n')
  await setupClerkTestingToken({ page })
  await page.goto('/signup?returnTo=' + encodeURIComponent(destination))
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByLabel('Confirm password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page.getByLabel('Verification code', { exact: true })).toBeVisible()
  return { email, password }
}

test('signed-in users leave auth pages, including after reload, and follow safe return routes', async ({ page, profile }) => {
  expect(profile.id).toBeTruthy()
  for (const path of ['/signup?returnTo=/app/settings', '/login?returnTo=/app/settings', '/forgot-password?returnTo=/app/settings']) {
    await page.goto(path)
    await expect(page).toHaveURL(/\/app\/settings$/)
    await expect(page.getByLabel('Password', { exact: true })).toHaveCount(0)
    await page.reload()
    await expect(page).toHaveURL(/\/app\/settings$/)
  }
  await page.goto('/signup?returnTo=https://example.com')
  await expect(page).toHaveURL(/\/app$/)

  expect(() => parseAccountProfile(profile)).not.toThrow()
  expect(profile.personal_node_id).not.toBe(profile.published_node_id)
  await page.reload()
  expect((await api<AccountProfile>(page, 'me')).body.id).toBe(profile.id)
  await page.goto('/app/personal')
  await expect(page.getByRole('heading', { name: 'Personal' })).toBeVisible()
  await page.locator('.shell-desktop').getByRole('button', { name: 'Open account menu' }).click()
  await page.getByRole('menuitem', { name: 'Sign out', exact: true }).click()
  await expect(page).toHaveURL(/\/login/)
  expect((await api(page, 'me', 'GET', undefined, false)).status).toBe(401)
})

test('signup rejects incorrect verification, resends, provisions once and follows a safe return route', async ({ page }) => {
  await signup(page, '/app/settings')
  await page.getByLabel('Verification code', { exact: true }).fill('111111')
  await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'That code is not correct.' })).toBeVisible()
  await page.getByRole('button', { name: 'Send a new code', exact: true }).click()
  await expect(page.getByText('A new code has been sent. Check your inbox.')).toBeVisible()
  await page.getByLabel('Verification code', { exact: true }).fill('424242')
  await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/settings$/)
  const first = (await api<AccountProfile>(page, 'me')).body
  expect(first.plan).toBe('FREE')
  expect(first.personal_node_id).not.toBe(first.published_node_id)
  await page.reload()
  const second = (await api<AccountProfile>(page, 'me')).body
  expect(second).toMatchObject({ id: first.id, personal_node_id: first.personal_node_id, published_node_id: first.published_node_id, library_node_id: first.library_node_id })
  const children = await api<{ nodes: unknown[] }>(page, `nodes?parent_id=${first.personal_node_id}`)
  expect(children.body.nodes).toEqual([])
  await page.goto('/app')
  await expect(page.getByRole('heading', { name: 'Your Library starts here.' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'A little room for new words.' })).toBeVisible()
  expect((await api<StudySummary>(page, 'study/progress')).body).toMatchObject({ total: 0, due: 0, new: 0, studied: 0 })
  const date = new Date().toISOString().slice(0, 10)
  expect((await api<StudyActivity>(page, `study/activity?start_date=${date}&end_date=${date}`)).body).toMatchObject({ applied_events: 0, practice_events: 0, current_streak: 0 })
})

for (const kind of ['wrong-password', 'nonexistent-user'] as const) test(`login ${kind} does not establish a backend session`, async ({ page }) => {
  await setupClerkTestingToken({ page })
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(kind === 'wrong-password' ? process.env.E2E_EMAIL_A! : `missing-${randomUUID()}+clerk_test@example.com`)
  await page.getByLabel('Password', { exact: true }).fill(randomUUID() + 'Wrong1!')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'The email or password is incorrect.' })).toBeVisible()
  expect((await api(page, 'me', 'GET', undefined, false)).status).toBe(401)
  await expect(page).toHaveURL(/\/login$/)
})

test('password reset verifies its code and the replacement password signs in', async ({ page }) => {
  const credentials = await signup(page)
  await page.getByLabel('Verification code', { exact: true }).fill('424242')
  await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  await expect(page).toHaveURL(/\/app$/)
  const before = (await api<AccountProfile>(page, 'me')).body
  await signOut(page)
  await page.goto('/forgot-password')
  await page.getByLabel('Email', { exact: true }).fill(credentials.email)
  await page.getByRole('button', { name: 'Send reset code', exact: true }).click()
  await page.getByLabel('Verification code', { exact: true }).fill('111111')
  await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'That code is not correct.' })).toBeVisible()
  await page.getByLabel('Verification code', { exact: true }).fill('424242')
  await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  const replacement = randomUUID() + 'NewAa1!'
  await page.getByLabel('New password', { exact: true }).fill(replacement)
  await page.getByLabel('Confirm password', { exact: true }).fill(replacement)
  await page.getByRole('button', { name: 'Reset password', exact: true }).click()
  await expect(page).toHaveURL(/\/app$/)
  expect((await api<AccountProfile>(page, 'me')).body.id).toBe(before.id)
  await signOut(page)
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(credentials.email)
  await page.getByLabel('Password', { exact: true }).fill(replacement)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await verifyDevice(page)
  await expect(page).toHaveURL(/\/app$/)
  expect((await api<AccountProfile>(page, 'me')).body.id).toBe(before.id)
})

test('real token refresh and a new-tab session preserve identity', async ({ page, profile }) => {
  const refreshed = await page.evaluate(async () => {
    const session = (window as unknown as { Clerk: { session: { getToken: (options: { skipCache: boolean }) => Promise<string> } } }).Clerk.session
    const token = await session.getToken({ skipCache: true })
    const response = await fetch('/api/v1/me', { headers: { Authorization: `Bearer ${token}` } })
    return { status: response.status, profile: await response.json() }
  })
  expect(refreshed).toMatchObject({ status: 200, profile: { id: profile.id } })
  const other = await page.context().newPage()
  try {
    await other.goto('/app/personal')
    expect((await api<AccountProfile>(other, 'me')).body.id).toBe(profile.id)
  } finally { await other.close() }
})

test('switching accounts removes private cached Library data and unsafe return URLs are rejected', async ({ page, nodes, profile }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [28] })
  const title = 'private-history-' + randomUUID()
  const conversation = (await api<Conversation>(page, 'assistant/conversations', 'POST', { title })).body
  await start(page, deck.id)
  const draft = await session(page, profile.id, deck.id)
  await page.goto(`/app/personal/${deck.id}`)
  await expect(page.getByRole('heading', { name: deck.name, exact: true })).toBeVisible()
  await signOut(page)
  await page.goto('/login?returnTo=https%3A%2F%2Fevil.invalid')
  const other = await signIn(page, 'B', '/login?returnTo=https%3A%2F%2Fevil.invalid')
  await expect(page).toHaveURL(/\/app$/)
  expect(other.id).not.toBe(profile.id)
  await page.goto(`/app/personal/${deck.id}`)
  await expect(page.getByRole('heading', { name: deck.name, exact: true })).not.toBeVisible()
  expect((await api(page, `nodes/${deck.id}`)).status).toBe(404)
  await page.goBack()
  await expect(page.getByRole('heading', { name: deck.name, exact: true })).not.toBeVisible()
  await page.goto('/app')
  await page.getByRole('button', { name: 'Open PycilAI', exact: true }).click()
  await page.getByRole('button', { name: 'Conversation history', exact: true }).click()
  await expect(page.getByRole('button', { name: `Delete conversation ${title}`, exact: true })).not.toBeVisible()
  expect((await api(page, `assistant/conversations/${conversation.id}`)).status).toBe(404)
  expect(await session(page, other.id, deck.id)).toBeNull()
  expect(await session(page, profile.id, deck.id)).toEqual(draft)
  await signOut(page)
  await signIn(page, 'A')
  expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204)
})

test('Google OAuth returns through the real callback when a dedicated Google test identity is configured', async ({ page }) => {
  test.skip(!process.env.E2E_GOOGLE_EMAIL || !process.env.E2E_GOOGLE_PASSWORD, 'Google end-to-end completion requires a dedicated provider test identity; no credentials are invented.')
  await setupClerkTestingToken({ page })
  await page.goto('/login')
  await page.getByRole('button', { name: 'Continue with Google' }).click()
  await expect(page).toHaveURL(/accounts\.google\.com/)
  await page.getByRole('textbox', { name: /Email or phone/ }).fill(process.env.E2E_GOOGLE_EMAIL!)
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await page.getByRole('textbox', { name: /Enter your password/ }).fill(process.env.E2E_GOOGLE_PASSWORD!)
  await page.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(page).toHaveURL(/\/app(?:\/|$)/)
  expect((await api(page, 'me')).status).toBe(200)
})

test('enabled TOTP challenges validate authenticator codes before accepting the backend identity', async ({ page }) => {
  const credentials = await signup(page)
  await page.getByLabel('Verification code', { exact: true }).fill('424242')
  await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  await expect(page).toHaveURL(/\/app$/)
  const profile = (await api<AccountProfile>(page, 'me')).body
  const enrollment = await page.evaluate(async () => {
    try { return { secret: (await (window as unknown as { Clerk: { user: { createTOTP: () => Promise<{ secret: string }> } } }).Clerk.user.createTOTP()).secret } }
    catch (error) { return { error: (error as { errors?: { code: string }[] }).errors?.[0]?.code ?? 'unknown' } }
  })
  test.skip(['totp_not_enabled', 'feature_not_enabled'].includes(enrollment.error ?? ''), 'The configured Clerk instance rejects TOTP enrollment because authenticator MFA is disabled.')
  expect(enrollment.error).toBeUndefined()
  const code = () => {
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
    const bits = [...enrollment.secret!.toUpperCase().replaceAll('=', '')].map(char => alphabet.indexOf(char).toString(2).padStart(5, '0')).join('')
    const key = Buffer.from(bits.match(/.{8}/g)!.map(byte => parseInt(byte, 2)))
    const counter = Buffer.alloc(8); counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)))
    const hash = createHmac('sha1', key).update(counter).digest(), offset = hash[hash.length - 1] & 15
    return ((hash.readUInt32BE(offset) & 0x7fffffff) % 1000000).toString().padStart(6, '0')
  }
  await page.evaluate(async code => { await (window as unknown as { Clerk: { user: { verifyTOTP: (data: { code: string }) => Promise<unknown> } } }).Clerk.user.verifyTOTP({ code }) }, code())
  await signOut(page)
  await page.getByLabel('Email', { exact: true }).fill(credentials.email)
  await page.getByLabel('Password', { exact: true }).fill(credentials.password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByText('Enter the code from your authenticator app.')).toBeVisible()
  await page.getByLabel('Verification code', { exact: true }).fill('000000')
  await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'That code is not correct.' })).toBeVisible()
  await page.getByLabel('Verification code', { exact: true }).fill(code())
  await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  await expect(page).toHaveURL(/\/app$/)
  expect((await api<AccountProfile>(page, 'me')).body.id).toBe(profile.id)
})

test('revoking a test-owned Clerk session removes private UI and exposes sign-in recovery', async ({ page }) => {
  const credentials = await signup(page)
  await page.getByLabel('Verification code', { exact: true }).fill('424242')
  await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  await expect(page).toHaveURL(/\/app$/)
  expect((await api(page, 'me')).status).toBe(200)
  const identity = await page.evaluate(() => {
    const clerk = (window as unknown as { Clerk: { session: { id: string }; user: { primaryEmailAddress: { emailAddress: string } } } }).Clerk
    return { session: clerk.session.id, email: clerk.user.primaryEmailAddress.emailAddress }
  })
  expect(identity.email).toBe(credentials.email)
  const response = await fetch(`https://api.clerk.com/v1/sessions/${identity.session}/revoke`, { method: 'POST', headers: { Authorization: `Bearer ${process.env.CLERK_SECRET_KEY}` } })
  expect(response.status).toBe(200)
  await page.reload()
  await expect(page.getByRole('link', { name: 'Sign in to your Home', exact: true })).toBeVisible()
  expect((await api(page, 'me', 'GET', undefined, false)).status).toBe(401)
  await page.getByRole('link', { name: 'Sign in to your Home', exact: true }).click()
  await expect(page).toHaveURL(/\/login\?returnTo=/)
})
