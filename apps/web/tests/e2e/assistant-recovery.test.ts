import type { Page } from '@playwright/test'
import { api } from './helpers/api'
import { signIn } from './helpers/auth'

import { randomUUID } from 'node:crypto'

import { expect,proTest,test } from './fixtures'

import type { Conversation,ConversationDetails } from '../../src/lib/assistant-api'

import { open,send } from './helpers/assistant'

test('Assistant can send another message after a sense tool error', async ({ page, profile }) => {
  expect(profile.id).toBeTruthy()
  test.skip(process.env.E2E_PROVIDER_PROFILE === 'live', 'Controlled inference forces an invalid sense ID.')
  await open(page)
  const created = page.waitForResponse(r => r.url().endsWith('/assistant/conversations') && r.request().method() === 'POST')
  const first = page.waitForResponse(r => r.url().endsWith('/assistant:run'))
  await send(page, 'E2E missing sense')
  const conversation: Conversation = await (await created).json()
  try {
    const response = await first
    const stream = await response.text()
    expect(stream).toContain('RUN_FINISHED')
    expect(stream).not.toContain('RUN_ERROR')
    await expect(page.locator('.ai-markdown').last()).toContainText('E2E recovered from a missing sense.')
    const next = page.waitForResponse(r => r.url().endsWith('/assistant:run'))
    await send(page, 'E2E continue after error')
    expect(await (await next).text()).not.toContain('RUN_ERROR')
    await expect(page.locator('.ai-markdown').last()).toContainText('E2E response saved through the native checkpoint.')
    await page.reload(); await open(page)
    await expect(page.locator('.ai-markdown').last()).toContainText('E2E response saved through the native checkpoint.')
  } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
})

test('Assistant recovers when its remembered conversation was deleted', async ({ page, profile }) => {
  expect(profile.id).toBeTruthy()
  const conversation = (await api<Conversation>(page, 'assistant/conversations', 'POST', { title: 'Deleted conversation' })).body
  expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204)
  await page.evaluate(id => {
    const sessionId = (window as unknown as { Clerk: { session: { id: string } } }).Clerk.session.id
    localStorage.setItem(`pycil:assistant:${sessionId}`, id)
  }, conversation.id)
  await page.reload()
  await open(page)
  expect(await page.evaluate(() => {
    const sessionId = (window as unknown as { Clerk: { session: { id: string } } }).Clerk.session.id
    return localStorage.getItem(`pycil:assistant:${sessionId}`)
  })).toBeNull()
  await expect(page.getByRole('complementary', { name: 'PycilAI', exact: true }).getByRole('alert')).toHaveCount(0)
})

function turn(id: string, content = 'E2E hello') {
  return { threadId: id, runId: randomUUID(), messages: [{ id: randomUUID(), role: 'user', content }], tools: [], state: {}, context: [], forwardedProps: {} }
}

async function run(page: Page, input: ReturnType<typeof turn>) {
  return page.evaluate(async input => {
    const token = await (window as unknown as { Clerk: { session: { getToken: () => Promise<string> } } }).Clerk.session.getToken()
    const response = await fetch('/api/v1/assistant:run', { method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify(input) })
    const body = await response.text()
    return { status: response.status, body, events: response.ok ? body.split('\n\n').filter(event => event.startsWith('data: ')).map(event => JSON.parse(event.slice(6))) as { type: string }[] : [] }
  }, input)
}

test('provider error in HTTP 200 is a failed stream; reopening preserves state and supports a new turn', async ({ page, profile }) => {
  expect(profile.id).toBeTruthy()
  await open(page)
  const created = page.waitForResponse(r => r.url().endsWith('/assistant/conversations') && r.request().method() === 'POST')
  await send(page, 'E2E fail')
  const conversation: Conversation = await (await created).json()
  try {
    await expect(page.getByRole('alert').filter({ hasText: /failed|interrupted/i }).first()).toBeVisible()
    await expect(page.getByText('E2E response saved through the native checkpoint.', { exact: true })).not.toBeVisible()
    await page.reload(); await open(page)
    await send(page, 'E2E recovery')
    await expect(page.getByText('E2E response saved through the native checkpoint.', { exact: true })).toBeVisible()
  } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
})

test('concurrent turns reject busy conversations and cancelling releases the native lock', async ({ page, profile }) => {
  expect(profile.id).toBeTruthy()
  await open(page)
  const created = page.waitForResponse(r => r.url().endsWith('/assistant/conversations') && r.request().method() === 'POST')
  await send(page, 'E2E slow')
  const conversation: Conversation = await (await created).json()
  try {
    await expect(page.getByRole('button', { name: 'Stop response', exact: true })).toBeVisible()
    const competing = await run(page, turn(conversation.id))
    expect(competing).toMatchObject({ status: 409 })
    expect(competing.body).toContain('conversation_busy')
    await page.getByRole('button', { name: 'Stop response', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Send message', exact: true })).toBeVisible()
    await expect.poll(async () => (await run(page, turn(conversation.id))).status).toBe(200)
  } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
})

test('an exhausted real usage period shows zero allowance and rejects the turn without automatic replay', async ({ page }) => {
  await signIn(page, 'C'); await open(page)
  await page.getByRole('button', { name: 'AI settings' }).click()
  await expect(page.getByRole('progressbar', { name: 'AI unit usage' })).toHaveAttribute('aria-valuenow', '100')
  await expect(page.getByText('Exhausted', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  const created = page.waitForResponse(r => r.url().endsWith('/assistant/conversations') && r.request().method() === 'POST')
  let runs = 0
  page.on('request', request => { if (request.url().endsWith('/assistant:run')) runs++ })
  await send(page, 'E2E exhausted')
  const conversation: Conversation = await (await created).json()
  try {
    await expect(page.getByRole('alert').filter({ hasText: /allowance|failed|could not/i }).first()).toBeVisible()
    expect(runs).toBe(1)
    expect((await api<ConversationDetails>(page, `assistant/conversations/${conversation.id}`)).body.state.messages).toEqual([])
  } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
})

proTest('native start rate limit rejects a burst and the Assistant UI never replays the rejected turn', async ({ page, profile }) => {
  test.setTimeout(120000)
  expect(profile.plan).toBe('PRO')
  const untilMinute = 60000 - Date.now() % 60000
  if (untilMinute < 15000) await new Promise(resolve => setTimeout(resolve, untilMinute + 100))
  const conversation = (await api<Conversation>(page, 'assistant/conversations', 'POST', { title: 'native rate limit' })).body
  try {
    let limited = false
    for (let attempt = 0; attempt < 42; attempt++) {
      const result = await run(page, turn(conversation.id))
      if (result.status === 429) { expect(result.body).toContain('assistant_start_limit'); limited = true; break }
      expect(result.status).toBe(200)
      expect(result.events.at(-1)?.type).toBe('RUN_FINISHED')
    }
    expect(limited).toBe(true)
    await open(page)
    let runs = 0
    page.on('request', request => { if (request.url().endsWith('/assistant:run')) runs++ })
    const created = page.waitForResponse(r => r.url().endsWith('/assistant/conversations') && r.request().method() === 'POST')
    await send(page, 'E2E rate limited')
    const rejected: Conversation = await (await created).json()
    try {
      await expect(page.getByRole('alert').filter({ hasText: /request limit|try again later/i }).first()).toBeVisible()
      expect(runs).toBe(1)
      expect((await api<ConversationDetails>(page, `assistant/conversations/${rejected.id}`)).body.state.messages).toEqual([])
    } finally { expect((await api(page, `assistant/conversations/${rejected.id}`, 'DELETE')).status).toBe(204) }
  } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
})
