import { api } from './helpers/api'
import { signIn } from './helpers/auth'


import { expect,test } from './fixtures'

import type { AssistantModel,Conversation,ConversationDetails,ConversationPage } from '../../src/lib/assistant-api'

import type { UsageAllowance } from '../../src/lib/api'

import { open,send } from './helpers/assistant'

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

test('Assistant renders native Library reads and hides another account’s private conversation and tool data', async ({ page, nodes, browser, baseURL, profile }) => {
  const deck = await nodes.create({ type: 'DECK' })
  await open(page)
  const created = page.waitForResponse(response => response.url().endsWith('/assistant/conversations') && response.request().method() === 'POST')
  const streamed = page.waitForResponse(response => response.url().endsWith('/assistant:run'))
  await send(page, 'E2E read node ' + deck.id)
  const conversation: Conversation = await (await created).json()
  const context = await browser.newContext({ baseURL })
  try {
    const response = await streamed
    expect(await response.text()).toContain('RUN_FINISHED')
    await expect(page.locator('.ai-markdown').last()).toContainText(deck.name)
    const other = await context.newPage()
    expect((await signIn(other, 'B')).id).not.toBe(profile.id)
    await open(other)
    await other.getByRole('button', { name: 'Conversation history', exact: true }).click()
    await expect(other.getByRole('button', { name: `Delete conversation ${conversation.title}`, exact: true })).toHaveCount(0)
    await other.getByRole('button', { name: 'Conversation history', exact: true }).click()
    const otherCreated = other.waitForResponse(response => response.url().endsWith('/assistant/conversations') && response.request().method() === 'POST')
    const deniedStream = other.waitForResponse(response => response.url().endsWith('/assistant:run'))
    await send(other, 'E2E read node ' + deck.id)
    const owned: Conversation = await (await otherCreated).json()
    try {
      const stream = await (await deniedStream).text()
      expect(stream).toContain('RUN_FINISHED')
      expect(stream).not.toContain(deck.name)
      const history = (await api<ConversationDetails>(other, `assistant/conversations/${owned.id}`)).body
      expect(history.state.messages).toContainEqual(expect.objectContaining({ role: 'tool', content: 'node_not_found' }))
      await expect(other.locator('.ai-markdown').last()).not.toContainText(deck.name)
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

test('valid vision reaches the checkpoint and invalid image uploads stay out of the composer', async ({ page, profile }) => {
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
  } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
})
