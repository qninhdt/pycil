import type { Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import { test, proTest, expect, api, signIn } from './fixtures'
import type { AssistantModel, Conversation, ConversationDetails, ConversationPage } from '../src/lib/assistant-api'
import type { UsageAllowance } from '../src/lib/api'

async function open(page: Page) {
  const panel = page.getByRole('complementary', { name: 'PycilAI', exact: true })
  const launcher = page.getByRole('button', { name: 'Open PycilAI', exact: true })
  await expect.poll(async () => await panel.isVisible() || await launcher.isVisible()).toBe(true)
  if (!await panel.isVisible()) await launcher.click()
  await expect(page.getByRole('textbox', { name: 'Message PycilAI' })).toBeVisible()
}
async function send(page: Page, message: string) {
  await page.getByRole('textbox', { name: 'Message PycilAI' }).fill(message)
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
}

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

test('Assistant streams reasoning and long text before completion without a whole-turn deadline', async ({ page, profile }) => {
  expect(profile.id).toBeTruthy()
  test.skip(process.env.E2E_PROVIDER_PROFILE === 'live', 'Controlled provider pauses verify transport deadlines.')
  test.setTimeout(110000)
  const created = page.waitForResponse(r => r.url().endsWith('/assistant/conversations') && r.request().method() === 'POST')
  let completed = false
  page.on('requestfinished', request => { if (request.url().endsWith('/assistant:run')) completed = true })
  await open(page)
  await send(page, 'E2E streaming across timeouts')
  const conversation: Conversation = await (await created).json()
  try {
    await expect(page.locator('.ai-reasoning-body')).toHaveText('E2E reasoning arrives before the answer.')
    await expect(page.locator('.ai-reasoning-body')).toBeVisible()
    expect(completed).toBe(false)
    await expect(page.locator('.ai-markdown').last()).toContainText('E2E first paragraph.')
    expect(completed).toBe(false)
    await expect(page.locator('.ai-markdown').last()).toContainText('A long continuation.', { timeout: 40000 })
    expect(completed).toBe(false)
    await expect(page.locator('.ai-markdown').last()).toContainText('E2E final paragraph.', { timeout: 40000 })
    await expect.poll(() => completed).toBe(true)
    await expect(page.locator('.ai-message-error, .ai-error')).toHaveCount(0)
    const saved = (await api<ConversationDetails>(page, `assistant/conversations/${conversation.id}`)).body
    expect(saved.state.messages.some(m => m.role === 'reasoning' && m.content === 'E2E reasoning arrives before the answer.')).toBe(true)
    await page.reload(); await open(page)
    await expect(page.locator('.ai-markdown').last()).toContainText('E2E final paragraph.')
    await page.locator('.ai-reasoning summary').click()
    await expect(page.locator('.ai-reasoning-body')).toBeVisible()
  } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
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

test('native SSE, model policy, checkpoint reload and usage settlement reach the Assistant UI', async ({ page, profile }) => {
  const models = (await api<AssistantModel[]>(page, 'assistant/models')).body
  const before = (await api<UsageAllowance>(page, 'me/usage')).body
  await open(page)
  await page.getByRole('button', { name: 'Choose model' }).click()
  await page.getByRole('button', { name: 'Select model' }).click()
  for (const model of models) await expect(page.getByRole('menuitemradio', { name: new RegExp(model.name) })).toBeVisible()
  await page.keyboard.press('Escape')
  const created = page.waitForResponse(response => response.url().endsWith('/assistant/conversations') && response.request().method() === 'POST')
  await send(page, 'E2E hello <img src=x onerror=alert(1)>')
  const conversation: Conversation = await (await created).json()
  try {
    await expect(page.getByText('E2E response saved through the native checkpoint.', { exact: true })).toBeVisible()
    const stored = (await api<ConversationDetails>(page, `assistant/conversations/${conversation.id}`)).body
    expect(stored.state.messages.some(message => message.role === 'user')).toBe(true)
    expect(stored.state.messages.some(message => message.role === 'assistant')).toBe(true)
    const usage = (await api<UsageAllowance>(page, 'me/usage')).body
    expect(usage.used_units).toBeGreaterThan(before.used_units)
    await page.reload(); await open(page)
    await expect(page.getByText('E2E response saved through the native checkpoint.', { exact: true })).toBeVisible()
    expect(await page.locator('img[src=x]').count()).toBe(0)
    expect(profile.plan).toBe('FREE')
  } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
})

for (const decision of ['approve', 'reject'] as const) test(`pending native Library mutation survives reload and ${decision} changes only authorized data`, async ({ page, profile, nodes }) => {
  const title = 'assistant-' + randomUUID()
  const created = page.waitForResponse(r => r.url().endsWith('/assistant/conversations') && r.request().method() === 'POST')
  await open(page); await send(page, 'E2E create deck ' + title)
  const conversation: Conversation = await (await created).json()
  try {
    await expect(page.getByRole('button', { name: 'Approve changes', exact: true })).toBeVisible()
    const lookup = async () => (await api<{ nodes: { id: string }[] }>(page, `nodes/${profile.personal_node_id}:search?q=${encodeURIComponent(title)}`)).body.nodes
    expect(await lookup()).toEqual([])
    const pending = (await api<ConversationDetails>(page, `assistant/conversations/${conversation.id}`)).body.state.pending_approvals
    expect(pending).toHaveLength(1)
    await page.reload(); await open(page)
    await expect(page.getByRole('button', { name: 'Approve changes', exact: true })).toBeVisible()
    expect((await api<ConversationDetails>(page, `assistant/conversations/${conversation.id}`)).body.state.pending_approvals).toEqual(pending)
    await page.getByRole('button', { name: decision === 'approve' ? 'Approve changes' : 'Reject', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Approve changes', exact: true })).not.toBeVisible()
    await expect.poll(async () => (await api<ConversationDetails>(page, `assistant/conversations/${conversation.id}`)).body.state.pending_approvals.length).toBe(0)
    const result = await lookup()
    expect(result).toHaveLength(decision === 'approve' ? 1 : 0)
    if (result.length) { nodes.track(result[0].id); await page.goto(`/app/personal/${result[0].id}`); await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible() }
  } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
})

test('read tools return real Library data and another account cannot read, run or delete its conversation', async ({ page, nodes, browser, baseURL, profile }) => {
  const deck = await nodes.create({ type: 'DECK' })
  const conversation = (await api<Conversation>(page, 'assistant/conversations', 'POST', { title: 'owned read tool' })).body
  const context = await browser.newContext({ baseURL })
  try {
    const events = await run(page, turn(conversation.id, 'E2E read node ' + deck.id))
    expect(events.events.at(-1)?.type).toBe('RUN_FINISHED')
    expect(events.body).toContain(deck.name)
    const other = await context.newPage()
    expect((await signIn(other, 'B')).id).not.toBe(profile.id)
    expect((await api(other, `assistant/conversations/${conversation.id}`)).status).toBe(404)
    expect((await api(other, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(404)
    expect((await run(other, turn(conversation.id))).status).toBe(404)
    const owned = (await api<Conversation>(other, 'assistant/conversations', 'POST', { title: 'unauthorized tool' })).body
    try {
      const denied = await run(other, turn(owned.id, 'E2E read node ' + deck.id))
      expect(denied.body).not.toContain(deck.name)
      expect(denied.events.at(-1)?.type).toBe('RUN_ERROR')
    } finally { expect((await api(other, `assistant/conversations/${owned.id}`, 'DELETE')).status).toBe(204) }
  } finally { await context.close(); expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
})

test('conversation history pages without duplicates and deletion requires confirmation', async ({ page, profile }) => {
  expect(profile.id).toBeTruthy()
  const owned: Conversation[] = []
  try {
    for (let n = 0; n < 21; n++) owned.push((await api<Conversation>(page, 'assistant/conversations', 'POST', { title: `native-history-${n}` })).body)
    const first = (await api<ConversationPage>(page, 'assistant/conversations?limit=20')).body
    const second = (await api<ConversationPage>(page, 'assistant/conversations?limit=20&cursor=' + encodeURIComponent(first.next_cursor!))).body
    expect(first.conversations).toHaveLength(20)
    expect(new Set([...first.conversations, ...second.conversations].map(item => item.id)).size).toBe(21)
    await open(page)
    await page.getByRole('button', { name: 'Conversation history', exact: true }).click()
    await page.getByRole('button', { name: 'Load older conversations' }).click()
    await expect(page.getByRole('button', { name: 'Delete conversation native-history-0', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Delete conversation native-history-0', exact: true }).click()
    await page.getByRole('alertdialog').getByRole('button', { name: 'Cancel', exact: true }).click()
    expect((await api(page, `assistant/conversations/${owned[0].id}`)).status).toBe(200)
    await page.getByRole('button', { name: 'Delete conversation native-history-0', exact: true }).click()
    await page.getByRole('alertdialog').getByRole('button', { name: 'Delete conversation', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Delete conversation native-history-0', exact: true })).not.toBeVisible()
    expect((await api(page, `assistant/conversations/${owned.shift()!.id}`)).status).toBe(404)
  } finally { for (const item of owned) expect((await api(page, `assistant/conversations/${item.id}`, 'DELETE')).status).toBe(204) }
})

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

test('valid vision reaches the checkpoint; unsupported image and model inputs cannot create turns', async ({ page, profile }) => {
  expect(profile.id).toBeTruthy()
  await open(page)
  const unsupportedImageChooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: 'Attach images', exact: true }).click()
  await (await unsupportedImageChooser).setFiles({ name: 'unsafe.svg', mimeType: 'image/svg+xml', buffer: Buffer.from('<svg/>') })
  await expect(page.getByRole('alert').filter({ hasText: /File type image\/svg\+xml is not accepted/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Remove unsafe.svg' })).not.toBeVisible()
  const oversizedImageChooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: 'Attach images', exact: true }).click()
  await (await oversizedImageChooser).setFiles({ name: 'large.png', mimeType: 'image/png', buffer: Buffer.alloc(10_000_001) })
  await expect(page.getByRole('alert').filter({ hasText: 'Use a PNG, JPEG or WebP image up to 10 MB.' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Remove large.png' })).not.toBeVisible()
  const created = page.waitForResponse(r => r.url().endsWith('/assistant/conversations') && r.request().method() === 'POST')
  const imageChooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: 'Attach images', exact: true }).click()
  await (await imageChooser).setFiles({ name: 'pixel.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jNn0AAAAASUVORK5CYII=', 'base64') })
  await expect(page.getByRole('button', { name: 'Remove pixel.png' })).toBeVisible()
  await send(page, 'E2E vision')
  const conversation: Conversation = await (await created).json()
  try {
    await expect(page.getByText('E2E response saved through the native checkpoint.', { exact: true })).toBeVisible()
    const saved = (await api<ConversationDetails>(page, `assistant/conversations/${conversation.id}`)).body
    expect(JSON.stringify(saved.state.messages)).toContain('image/png')
    const invalid = { ...turn(conversation.id), forwardedProps: { model_id: 'missing-model', effort: 'none' } }
    expect((await run(page, invalid)).status).toBe(422)
    const bad = turn(conversation.id)
    Object.assign(bad.messages[0], { content: [{ type: 'image', source: { type: 'data', mimeType: 'image/svg+xml', value: Buffer.from('<svg/>').toString('base64') } }] })
    expect((await run(page, bad)).status).toBe(422)
  } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
})

test('an exhausted real usage period shows zero allowance and rejects the turn without automatic replay', async ({ page }) => {
  await signIn(page, 'C'); await open(page)
  await expect(page.getByText(/0 of 1,000,000 AI units remaining/)).toBeVisible()
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
