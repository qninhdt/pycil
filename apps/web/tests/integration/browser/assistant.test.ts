import database from '../../../src/lib/services/mock/database'

import { expect,test,type Page } from '@playwright/test'

import { buildFixture,renderFixture } from './fixtures/render-fixture'


import type { RunAgentInput } from '@ag-ui/core'

const model = { id: 'vision-model', name: 'Vision model', vision: true, efforts: ['low', 'medium', 'high'] }

const id = '01900000-0000-7000-8000-000000000001'

const secondId = '01900000-0000-7000-8000-000000000002'

const metadata = { id, title: 'Discover or invent?', updated_at: '2026-10-08T03:00:00Z' }

const state = { messages: [{ id: 'old-user', role: 'user', content: 'A saved question' }, { id: 'old-assistant', role: 'assistant', content: 'A saved answer.' }], pending_approvals: [] }


let bundle: string

test.beforeAll(async () => {
  const account = `export function useAccount(){return {status:'ready',signedIn:true,profile:null,name:'Test learner',signOut:async()=>{}}}; export function useTheme(){return {theme:'light',toggleTheme:()=>{}}}`
  bundle = await buildFixture('assistant', { '@/components/application/providers': account, './providers': account })
})

async function fixture(page: Page) {
  await renderFixture(page, bundle, 'assistant')
}

async function openAssistant(page: Page) {
  const panel = page.getByRole('complementary', { name: 'PycilAI', exact: true })
  const launcher = page.getByRole('button', { name: /^(Open PycilAI|PycilAI)$/ })
  await expect.poll(async () => await panel.isVisible() || await launcher.isVisible()).toBe(true)
  if (!await panel.isVisible()) await launcher.click()
}

function events(runId: string, text = 'A streamed answer.', reasoning = '**Considering car wash logistics**\n\nBring the car to wash it.') {
  return [
    { type: 'RUN_STARTED', threadId: id, runId },
    { type: 'REASONING_START', messageId: 'reasoning-' + runId },
    { type: 'REASONING_MESSAGE_START', messageId: 'reasoning-' + runId, role: 'reasoning' },
    { type: 'REASONING_MESSAGE_CONTENT', messageId: 'reasoning-' + runId, delta: reasoning },
    { type: 'REASONING_MESSAGE_END', messageId: 'reasoning-' + runId },
    { type: 'REASONING_END', messageId: 'reasoning-' + runId },
    { type: 'TEXT_MESSAGE_START', messageId: 'answer-' + runId, role: 'assistant' },
    { type: 'TEXT_MESSAGE_CONTENT', messageId: 'answer-' + runId, delta: text },
    { type: 'TEXT_MESSAGE_END', messageId: 'answer-' + runId },
    { type: 'RUN_FINISHED', threadId: id, runId },
  ].map(event => `data: ${JSON.stringify(event)}\n\n`).join('')
}

async function mockApi(page: Page, options: { pending?: boolean; error?: boolean; answer?: string; reasoning?: string; history?: RunAgentInput['messages'] } = {}) {
  const requests: RunAgentInput[] = []
  await page.route('**/*v1/me', route => route.fulfill({ json: database.account }))
  await page.route('**/*v1/me/usage', route => route.fulfill({ json: { period_start: '2026-10-01T00:00:00Z', period_end: '2026-11-01T00:00:00Z', allowance_units: 1000, used_units: 0, remaining_units: 1000 } }))
  await page.route('**/*v1/assistant**', async route => {
    const request = route.request(), url = new URL(request.url())
    expect(request.headers().authorization).toBe('Bearer test-only-bearer')
    if (url.pathname.endsWith('/models')) return route.fulfill({ json: [model, { ...model, id: 'text-model', name: 'Text model', vision: false }] })
    if (url.pathname.endsWith('/conversations') && request.method() === 'GET') return route.fulfill({ json: { conversations: [metadata], next_cursor: url.searchParams.has('cursor') ? null : 'older-page' } })
    if (url.pathname.endsWith('/conversations') && request.method() === 'POST') return route.fulfill({ status: 201, json: { ...metadata, id: secondId, title: request.postDataJSON().title } })
    if (url.pathname.includes('/conversations/')) return route.fulfill({ json: { ...metadata, id: url.pathname.split('/').at(-1), state: options.pending ? { messages: [...state.messages, { id: 'pending-assistant', role: 'assistant', content: '', toolCalls: [{ id: 'tool-1', type: 'function', function: { name: 'create_node', arguments: '{"name":"New deck"}' } }] }], pending_approvals: [{ interrupt_id: 'interrupt-1', action_requests: [{ name: 'create_node', args: { name: 'New deck' } }] }] } : { ...state, messages: options.history ?? state.messages } } })
    expect(url.pathname.endsWith('/assistant:run')).toBe(true)
    expect(request.method()).toBe('POST')
    const input = request.postDataJSON() as RunAgentInput
    requests.push(input)
    if (options.error) return route.fulfill({ status: 409, json: { error: 'conversation_busy' } })
    return route.fulfill({ contentType: 'text/event-stream', body: events(input.runId, options.answer, options.reasoning) })
  })
  return requests
}

test('Assistant auto approval persists through API and failed writes keep the saved setting', async ({ page }) => {
  await mockApi(page)
  const profile = structuredClone(database.account)
  let failed = false
  const patches: unknown[] = []
  await page.route('**/*v1/me', route => route.fulfill({ json: profile }))
  await page.route('**/*v1/me/settings', route => {
    expect(route.request().method()).toBe('PATCH')
    const patch = route.request().postDataJSON()
    patches.push(patch)
    if (failed) return route.fulfill({ status: 503, json: { error: 'settings_unavailable' } })
    profile.settings.assistant = patch.assistant
    return route.fulfill({ json: profile })
  })
  await fixture(page)
  await openAssistant(page)
  await page.getByRole('button', { name: 'AI settings' }).click()
  const toggle = page.getByRole('switch', { name: 'Auto-approve actions' })
  await expect(toggle).not.toBeChecked()
  await expect(toggle).toBeEnabled()
  await toggle.click()
  await expect(toggle).toBeChecked()
  expect(patches).toEqual([{ assistant: { auto_approve: true } }])
  await page.reload()
  await openAssistant(page)
  await page.getByRole('button', { name: 'AI settings' }).click()
  await expect(toggle).toBeChecked()
  failed = true
  await toggle.click()
  await expect(toggle).toBeEnabled()
  await expect(toggle).toBeChecked()
  expect(patches).toEqual([{ assistant: { auto_approve: true } }, { assistant: { auto_approve: false } }])
})

test('showcase exercises reasoning, models, attachments, history and approval', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/showcase?view=assistant')
  await expect(page.locator('.ai-message-user')).toHaveCount(4)
  await expect(page.locator('.ai-message-content').first()).toHaveCSS('border-radius', '0px')
  await page.locator('.ai-reasoning > summary').first().click()
  await expect(page.getByText(/cross-deck spaced repetition backlog/)).toBeVisible()
  await page.getByRole('button', { name: 'Choose model' }).click()
  const popover = page.locator('.ai-model-popover')
  await expect(popover).toHaveCSS('box-shadow', 'none')
  const track = page.locator('.ai-effort-track')
  const thumb = page.locator('.ai-effort-thumb')
  await expect(thumb).toHaveCSS('box-shadow', 'none')
  const trackBox = (await track.boundingBox())!
  const thumbBox = (await thumb.boundingBox())!
  expect(Math.abs((trackBox.y + trackBox.height / 2) - (thumbBox.y + thumbBox.height / 2))).toBeLessThanOrEqual(1)

  // Drag slider left to Low
  await page.mouse.move(trackBox.x + trackBox.width / 2, trackBox.y + trackBox.height / 2)
  await page.mouse.down()
  await page.mouse.move(trackBox.x + 5, trackBox.y + trackBox.height / 2)
  await page.mouse.up()
  await expect(track).toHaveAttribute('aria-valuenow', '0')

  // Drag slider right to High
  await page.mouse.move(trackBox.x + 5, trackBox.y + trackBox.height / 2)
  await page.mouse.down()
  await page.mouse.move(trackBox.x + trackBox.width - 5, trackBox.y + trackBox.height / 2)
  await page.mouse.up()
  await expect(track).toHaveAttribute('aria-valuenow', '2')

  await page.getByRole('button', { name: 'Select model' }).click()
  await page.getByRole('menuitemradio', { name: 'Text model · Preview' }).click()
  await expect(page.getByLabel('Attach images', { exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Choose model' }).click()
  await page.getByRole('button', { name: 'Select model' }).click()
  await page.getByRole('menuitemradio', { name: 'Vision model · Preview' }).click()
  const imageChooser = page.waitForEvent('filechooser')
  await page.getByRole('button', { name: 'Attach images', exact: true }).click()
  await (await imageChooser).setFiles({ name: 'geometry.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl9sAAAAASUVORK5CYII=', 'base64') })
  await expect(page.getByRole('button', { name: 'Remove geometry.png' })).toBeVisible()
  await page.getByRole('button', { name: 'Remove geometry.png' }).click()
  await page.getByLabel('Message PycilAI').fill('Keep this draft')
  await page.getByRole('button', { name: 'Preview conversation history' }).click()
  await expect(page.getByRole('textbox', { name: 'Message PycilAI' })).toHaveCount(0)
  await page.keyboard.press('Tab')
  await expect(page.locator('.ai-input')).not.toBeFocused()
  await page.getByRole('button', { name: 'Back to preview conversation' }).click()
  await expect(page.getByLabel('Message PycilAI')).toHaveValue('Keep this draft')
  await page.getByRole('button', { name: 'Preview conversation history' }).click()
  await page.getByRole('button', { name: /Words worth keeping/ }).click()
  await expect(page.getByText('Illustrative saved conversation. The live app loads your own conversation history.')).toBeVisible()
  await page.getByRole('button', { name: 'Approval state' }).click()
  await page.getByRole('button', { name: 'Reject', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Preview rejected')
  await page.getByRole('button', { name: 'New preview conversation' }).click()
  await page.getByLabel('Message PycilAI').fill('Try a new idea')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.ai-message-assistant')).toContainText('This is a design preview')
  expect(errors).toEqual([])
})

test('a missing remembered conversation opens a new chat and clears its stale id', async ({ page }) => {
  await page.addInitScript(value => localStorage.setItem('pycil:assistant:assistant-test', value), id)
  const requests = await mockApi(page)
  let reads = 0
  await page.route(`**/*v1/assistant/conversations/${id}`, route => {
    reads++
    return route.fulfill({ status: 404, json: { error: 'not_found' } })
  })
  await fixture(page)
  await openAssistant(page)
  await page.getByLabel('Message PycilAI').fill('A new conversation')
  expect(await page.evaluate(() => localStorage.getItem('pycil:assistant:assistant-test'))).toBeNull()
  expect(reads).toBe(1)
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.ai-message-assistant')).toContainText('A streamed answer.')
  expect(requests).toHaveLength(1)
})

test('a temporary conversation failure preserves its remembered id', async ({ page }) => {
  await page.addInitScript(value => localStorage.setItem('pycil:assistant:assistant-test', value), id)
  await mockApi(page)
  await page.route(`**/*v1/assistant/conversations/${id}`, route => route.fulfill({ status: 503, json: { error: 'unavailable' } }))
  await fixture(page)
  await openAssistant(page)
  await expect(page.getByRole('alert')).toContainText('Couldn’t open PycilAI.', { timeout: 15000 })
  expect(await page.evaluate(() => localStorage.getItem('pycil:assistant:assistant-test'))).toBe(id)
})

test('live panel sends a bounded new turn, streams, reopens history and restores focus', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const requests = await mockApi(page)
  await fixture(page)
  const launcher = page.getByRole('button', { name: /^(Open PycilAI|PycilAI)$/ })
  await launcher.click()
  await page.getByLabel('Message PycilAI').fill('Please explain discovery')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.ai-message-assistant')).toContainText('A streamed answer.')
  await page.locator('.ai-reasoning > summary').click()
  await expect(page.locator('.ai-reasoning-body strong')).toHaveText('Considering car wash logistics')
  await expect(page.locator('.ai-reasoning-body p')).toHaveCount(2)
  await expect(page.locator('.ai-reasoning-body')).not.toContainText('**')
  const reasoningMarkdown = page.locator('.ai-reasoning-body .ai-markdown')
  await expect(reasoningMarkdown).toHaveCSS('white-space', 'normal')
  const paragraphGap = await reasoningMarkdown.locator('p').evaluateAll(nodes => nodes[1].getBoundingClientRect().top - nodes[0].getBoundingClientRect().bottom)
  expect(paragraphGap).toBeCloseTo(12, 0)
  expect(requests[0]).toMatchObject({ threadId: secondId, messages: [{ role: 'user', content: 'Please explain discovery' }], state: {}, tools: [], context: [], forwardedProps: { model_id: model.id, effort: 'medium', current_view: { path: '/__assistant_fixture__', node_id: id } } })
  await page.getByRole('button', { name: 'Close PycilAI' }).click()
  await expect(launcher).toBeFocused()
  await launcher.click()
  await expect(page.locator('.ai-message-assistant')).toContainText('A saved answer.')
  await page.getByLabel('Message PycilAI').fill('A live draft')
  await page.getByRole('button', { name: 'Conversation history' }).click()
  await expect(page.getByRole('textbox', { name: 'Message PycilAI' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Back to conversation', exact: true }).click()
  await expect(page.getByLabel('Message PycilAI')).toHaveValue('A live draft')
  await page.getByRole('button', { name: 'Conversation history' }).click()
  await expect(page.getByRole('button', { name: 'Load older conversations' })).toBeVisible()
  await page.getByRole('button', { name: /^Discover or invent/ }).click()
  await expect(page.locator('.ai-message-user')).toContainText('A saved question')
  await page.getByRole('button', { name: 'Switch current view' }).click()
  await page.getByLabel('Message PycilAI').fill('Follow up')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => requests.length).toBe(2)
  expect(requests[1].messages).toHaveLength(1)
  expect(requests[1].messages[0]).toMatchObject({ content: 'Follow up' })
  expect(requests[1].forwardedProps).toMatchObject({ current_view: { path: '/__assistant_fixture__', word_id: 1 } })
  expect((requests[1].forwardedProps as { current_view: object }).current_view).not.toHaveProperty('node_id')
  await page.keyboard.press('Escape')
  await expect(launcher).toBeFocused()
  expect(errors).toEqual([])
})

test('persisted approvals resume with matching interrupt and no transcript', async ({ page }) => {
  const requests = await mockApi(page, { pending: true })
  await fixture(page)
  await openAssistant(page)
  await page.getByRole('button', { name: 'Conversation history' }).click()
  await page.getByRole('button', { name: /^Discover or invent/ }).click()
  await page.getByRole('button', { name: 'Reject', exact: true }).click()
  await expect.poll(() => requests.length).toBe(1)
  expect(requests[0]).toMatchObject({ threadId: id, messages: [], resume: [{ interruptId: 'interrupt-1', status: 'resolved', payload: { decisions: [{ type: 'reject' }] } }] })
})

for (const earlyReasoning of [true, false]) test(`one thought per turn survives incremental tool rounds and history reload (early reasoning: ${earlyReasoning})`, async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const history: RunAgentInput['messages'] = []
  await mockApi(page, { history })
  await fixture(page)
  // Keep the response open so assertions inspect each streaming phase, not just the final DOM.
  await page.evaluate(() => {
    const originalFetch = window.fetch.bind(window)
    window.fetch = async (input, init) => {
      if (!String(input).endsWith('/assistant:run')) return originalFetch(input, init)
      const request = JSON.parse(String(init?.body))
      const encoder = new TextEncoder()
      const stream = new ReadableStream({ start(controller) {
        Object.assign(window, {
          pushAssistantEvents: (events: object[]) => events.forEach(event => controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`))),
          finishAssistantStream: () => {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'RUN_FINISHED', threadId: request.threadId, runId: request.runId })}\n\n`))
            controller.close()
          },
        })
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'RUN_STARTED', threadId: request.threadId, runId: request.runId })}\n\n`))
      } })
      return new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } })
    }
  })
  const push = async (events: object[]) => page.evaluate(events => (window as any).pushAssistantEvents(events), events)
  const reasoning = (index: number) => [
    { type: 'REASONING_START', messageId: `reason-${index}` },
    { type: 'REASONING_MESSAGE_START', messageId: `reason-${index}`, role: 'reasoning' },
    { type: 'REASONING_MESSAGE_CONTENT', messageId: `reason-${index}`, delta: `Reasoning step ${index}.` },
    { type: 'REASONING_MESSAGE_END', messageId: `reason-${index}` },
    { type: 'REASONING_END', messageId: `reason-${index}` },
  ]
  await openAssistant(page)
  await page.getByLabel('Message PycilAI').fill('Inspect then update my library')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => page.evaluate(() => typeof (window as any).pushAssistantEvents)).toBe('function')
  history.push({ id: 'request', role: 'user', content: 'Inspect then update my library' })
  for (const index of [1, 2]) {
    const toolName = index === 1 ? 'search_nodes' : 'generate_words'
    const args = index === 1 ? { queries: ['Hogwarts'] } : { words: ['deadline', 'delegate', 'negotiate', 'clarify', 'persuade', 'interrupt', 'evaluate', 'prioritize', 'assume'] }
    const result = index === 1 ? '{"nodes":[]}' : '{"items":[]}'
    await push([
      ...(earlyReasoning ? reasoning(index) : []),
      { type: 'TEXT_MESSAGE_START', messageId: `message-${index}`, role: 'assistant' },
      { type: 'TOOL_CALL_START', toolCallId: `call-${index}`, toolCallName: toolName, parentMessageId: `message-${index}` },
      { type: 'TOOL_CALL_ARGS', toolCallId: `call-${index}`, delta: JSON.stringify(args) },
      { type: 'TOOL_CALL_END', toolCallId: `call-${index}` },
      { type: 'TEXT_MESSAGE_END', messageId: `message-${index}` },
    ])
    await expect(page.locator('.ai-reasoning')).toHaveCount(1)
    if (earlyReasoning) await expect(page.locator('.ai-reasoning-body')).toContainText(`Reasoning step ${index}.`)
    await expect(page.locator('.ai-tool')).toHaveCount(index)
    if (index === 2) {
      for (const width of [1440, 390]) {
        await page.setViewportSize({ width, height: 1000 })
        const tool = page.locator('.ai-tool').last()
        await expect(tool.locator('.ai-tool-title')).toHaveText('Prepare Vocabulary')
        await expect(tool.locator('.ai-tool-status[data-running]')).toBeVisible()
        for (const selector of ['.ai-tool-title', '.ai-tool-status']) {
          const dimensions = await tool.locator(selector).evaluate(element => {
            const rect = element.getBoundingClientRect(), parent = element.closest('summary')!.getBoundingClientRect()
            return { height: rect.height, lineHeight: parseFloat(getComputedStyle(element).lineHeight), left: rect.left, right: rect.right, parentLeft: parent.left, parentRight: parent.right }
          })
          expect(dimensions.height).toBeLessThan(dimensions.lineHeight * 2)
          expect(dimensions.left).toBeGreaterThanOrEqual(dimensions.parentLeft)
          expect(dimensions.right).toBeLessThanOrEqual(dimensions.parentRight)
        }
        const bounds = await tool.locator('summary').evaluate(element => ({ title: element.querySelector('.ai-tool-title')!.getBoundingClientRect().right, status: element.querySelector('.ai-tool-status')!.getBoundingClientRect().left }))
        expect(bounds.title).toBeLessThanOrEqual(bounds.status)
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      }
      await page.setViewportSize({ width: 1440, height: 1000 })
    }
    await push([{ type: 'TOOL_CALL_RESULT', messageId: `result-${index}`, toolCallId: `call-${index}`, role: 'tool', content: result }])
    history.push(
      ...(earlyReasoning ? [{ id: `reason-${index}`, role: 'reasoning' as const, content: `Reasoning step ${index}.` }] : []),
      { id: `message-${index}`, role: 'assistant', content: '', toolCalls: [{ id: `call-${index}`, type: 'function', function: { name: toolName, arguments: JSON.stringify(args) } }] },
      { id: `result-${index}`, role: 'tool', toolCallId: `call-${index}`, content: result },
    )
  }
  await push([...reasoning(3),
    { type: 'TEXT_MESSAGE_START', messageId: 'answer', role: 'assistant' },
    { type: 'TEXT_MESSAGE_CONTENT', messageId: 'answer', delta: 'The library update is complete.' },
    { type: 'TEXT_MESSAGE_END', messageId: 'answer' },
  ])
  history.push({ id: 'reason-3', role: 'reasoning', content: 'Reasoning step 3.' }, { id: 'answer', role: 'assistant', content: 'The library update is complete.' })
  await push([{ type: 'MESSAGES_SNAPSHOT', messages: history }])
  await page.evaluate(() => (window as any).finishAssistantStream())
  await expect(page.getByRole('button', { name: 'Send message' })).toBeVisible()
  await expect(page.locator('.ai-reasoning')).toHaveCount(1)
  await expect(page.locator('.ai-reasoning')).not.toHaveAttribute('open')
  await page.locator('.ai-reasoning > summary').click()
  for (const index of (earlyReasoning ? [1, 2, 3] : [3])) await expect(page.locator('.ai-reasoning-body')).toContainText(`Reasoning step ${index}.`)
  await expect(page.locator('.ai-tool')).toHaveCount(2)
  await expect(page.getByRole('button', { name: 'Copy response' })).toHaveCount(1)
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.getByRole('button', { name: 'Copy response' }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('The library update is complete.')
  // A new user turn must get a separate thought, even in the same conversation.
  await page.getByLabel('Message PycilAI').fill('One more question')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.getByRole('button', { name: 'Stop response' })).toBeVisible()
  await push([...reasoning(4), { type: 'TEXT_MESSAGE_START', messageId: 'answer-2', role: 'assistant' }, { type: 'TEXT_MESSAGE_CONTENT', messageId: 'answer-2', delta: 'Another answer.' }])
  await page.evaluate(() => (window as any).finishAssistantStream())
  await expect(page.locator('.ai-reasoning')).toHaveCount(2)
  history.push({ id: 'request-2', role: 'user', content: 'One more question' }, { id: 'reason-4', role: 'reasoning', content: 'Reasoning step 4.' }, { id: 'answer-2', role: 'assistant', content: 'Another answer.' })
  await page.reload()
  await openAssistant(page)
  await expect(page.locator('.ai-reasoning')).toHaveCount(2)
  await page.locator('.ai-reasoning > summary').first().click()
  for (const index of (earlyReasoning ? [1, 2, 3] : [3])) await expect(page.locator('.ai-reasoning-body').first()).toContainText(`Reasoning step ${index}.`)
  await expect(page.locator('.ai-tool')).toHaveCount(2)
  expect(errors).toEqual([])
})

test('multi-step tools and reasoning use the available width without empty copy rows', async ({ page }) => {
  const history: RunAgentInput['messages'] = [{ id: 'request', role: 'user', content: 'Read my library before writing the essay.' }, { id: 'thinking', role: 'reasoning', content: 'First inspect the available folders.' }]
  for (const [index, name] of ['search_nodes', 'read_library', 'read_library'].entries()) {
    history.push(
      { id: `step-${index}`, role: 'assistant', content: '', toolCalls: [{ id: `call-${index}`, type: 'function', function: { name, arguments: index === 0 ? '{"queries":["Messi vs Ronaldo"]}' : '{"view":"structure"}' } }] },
      { id: `result-${index}`, role: 'tool', toolCallId: `call-${index}`, content: JSON.stringify(index === 0 ? { nodes: [] } : { node: { name: 'Library', type: 'folder' }, nodes: [], next_cursor: null }) },
    )
  }
  history.push({ id: 'answer', role: 'assistant', content: 'The folder is empty. I can write the essay here.' })
  await mockApi(page, { history })
  await fixture(page)
  await openAssistant(page)
  await page.getByRole('button', { name: 'Conversation history' }).click()
  await page.getByRole('button', { name: /^Discover or invent/ }).click()
  await expect(page.locator('.ai-tool')).toHaveCount(3)
  await expect(page.getByRole('button', { name: 'Copy response' })).toHaveCount(1)
  await page.locator('.ai-reasoning > summary').click()
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 })
    const messages = page.locator('.ai-message-assistant')
    const geometry = await messages.evaluateAll(elements => elements.map(element => {
      const content = element.querySelector('.ai-message-content')!
      const details = content.querySelector('details')
      return { width: element.getBoundingClientRect().width, contentWidth: content.getBoundingClientRect().width, detailsWidth: details?.getBoundingClientRect().width, top: element.getBoundingClientRect().top, bottom: element.getBoundingClientRect().bottom }
    }))
    for (const [index, bounds] of geometry.entries()) {
      expect(bounds.contentWidth).toBeCloseTo(bounds.width, 0)
      if (bounds.detailsWidth !== undefined) expect(bounds.detailsWidth).toBeCloseTo(bounds.width, 0)
      if (index > 0) expect(bounds.top - geometry[index - 1].bottom).toBeCloseTo(24, 0)
    }
    await expect(messages.first().locator('.ai-message-content')).toHaveCSS('border-top-width', '0px')
    await expect(messages.first().locator('.ai-message-content')).toHaveCSS('padding-top', '0px')
    const thought = page.locator('.ai-reasoning')
    const tool = page.locator('.ai-tool').first()
    const chevronDirection = (collapse: typeof tool) => collapse.locator(':scope > summary > svg:last-child').evaluate(element => new DOMMatrix(getComputedStyle(element).transform).m11)
    await expect.poll(() => chevronDirection(thought)).toBe(-1)
    await expect.poll(() => chevronDirection(tool)).toBe(1)
    await tool.locator(':scope > summary').click()
    await expect.poll(() => chevronDirection(tool)).toBe(-1)
    await expect(page.locator('.ai-tool-body').first()).toContainText('Messi vs Ronaldo')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await tool.locator(':scope > summary').press('Enter')
    await expect.poll(() => chevronDirection(tool)).toBe(1)
    await expect.poll(() => chevronDirection(thought)).toBe(-1)
    await thought.locator(':scope > summary').click()
    await expect.poll(() => chevronDirection(thought)).toBe(1)
    await thought.locator(':scope > summary').click()
    await expect.poll(() => chevronDirection(tool)).toBe(1)
  }
})

test('reasoning and answers render dollar and TeX math while code remains literal', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const literalCode = '`\\(x^2\\)`'
  const markdown = String.raw`**Evaluating integral constants**

Inline \(\ln(1-x)\) and $x^2$.**Exploring series and sums**

Continuing the calculation.

\[
I = -2\sum_{n=1}^{\infty}\frac{x^n}{n}
\]

$$
\boxed{I=2\operatorname{Li}_{3,1}(-1,-1)}
$$

Literal code: ${literalCode}.

Invalid formula: \(\frac{1}\).`
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await mockApi(page, { answer: markdown, reasoning: markdown })
  await fixture(page)
  await openAssistant(page)
  await page.getByLabel('Message PycilAI').fill('Explain the integral')
  await page.getByRole('button', { name: 'Send message' }).click()
  await page.locator('.ai-reasoning > summary').click()
  for (const scope of [page.locator('.ai-reasoning-body'), page.locator('.ai-message-assistant .ai-message-content > .ai-markdown')]) {
    await expect(scope.locator('.katex')).toHaveCount(4)
    await expect(scope.locator('.katex-display')).toHaveCount(2)
    for (const formula of await scope.locator('.katex-display').all()) {
      await expect(formula).toHaveCSS('overflow-y', 'hidden')
      const dimensions = await formula.evaluate(element => ({ client: element.clientHeight, scroll: element.scrollHeight, height: element.getBoundingClientRect().height, math: element.querySelector('.katex-html')?.getBoundingClientRect().height, width: element.clientWidth, scrollWidth: element.scrollWidth }))
      expect(dimensions.scroll - dimensions.client, JSON.stringify(dimensions)).toBeLessThanOrEqual(1)
    }
    await expect(scope.locator('code').filter({ hasText: '\\(x^2\\)' })).toBeVisible()
    await expect(scope.locator('.katex-error')).toHaveCount(1)
  }
  await expect(page.locator('.ai-reasoning-body strong').last()).toHaveCSS('display', 'block')
  await expect(page.locator('.ai-message-content > .ai-markdown strong').last()).toHaveCSS('display', 'inline')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await expect(page.locator('.ai-message-error, .ai-error')).toHaveCount(0)
  expect(errors).toEqual([])
})

test('failed turns expose recovery without automatic replay', async ({ page }) => {
  const requests = await mockApi(page, { error: true })
  await fixture(page)
  await openAssistant(page)
  await page.getByLabel('Message PycilAI').fill('A question')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.ai-error')).toContainText('conversation is busy')
  expect(requests).toHaveLength(1)
})

test('assistant layouts stay inside desktop/mobile light/dark viewports', async ({ page }) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 1440 ? 1000 : 844 })
    for (const theme of ['light', 'dark']) {
      await page.goto('/showcase?view=assistant')
      await expect(page.getByRole('heading', { name: 'An assistant, in good form.' })).toBeVisible()
      await page.evaluate(theme => document.documentElement.classList.toggle('dark', theme === 'dark'), theme)
      await page.evaluate(() => document.fonts.ready)
      await page.locator('.ai-viewport').evaluate(element => { element.scrollTop = 0 })
      await page.evaluate(() => window.scrollTo(0, 0))
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    }
    await mockApi(page)
    await fixture(page)
    await openAssistant(page)
    await expect(page.getByLabel('Message PycilAI')).toBeVisible()
    const panel = page.locator('.ai-panel')
    const bounds = (await panel.boundingBox())!
    expect(bounds.x).toBeGreaterThanOrEqual(0)
    expect(bounds.width).toBeLessThanOrEqual(width)
    await page.getByRole('button', { name: 'Choose model' }).click()
    await page.getByRole('button', { name: 'Select model' }).click()
    await expect(page.getByRole('menuitemradio', { name: 'Vision model' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('menuitemradio', { name: 'Vision model' })).not.toBeVisible()
    await page.getByRole('button', { name: 'Close PycilAI' }).click()
  }
})
