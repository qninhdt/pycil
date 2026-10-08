import { test, expect, type Page } from '@playwright/test'
import { build } from 'esbuild'
import { mkdirSync } from 'node:fs'
import { turnInput, parseConversationDetails } from '../src/lib/assistant-api'
import type { RunAgentInput } from '@ag-ui/core'

const model = { id: 'vision-model', name: 'Vision model', vision: true, efforts: ['low', 'medium', 'high'] }
const id = '01900000-0000-7000-8000-000000000001'
const secondId = '01900000-0000-7000-8000-000000000002'
const metadata = { id, title: 'Discover or invent?', updated_at: '2026-10-08T03:00:00Z' }
const state = { messages: [{ id: 'old-user', role: 'user', content: 'A saved question' }, { id: 'old-assistant', role: 'assistant', content: 'A saved answer.' }], pending_approvals: [] }
const input: RunAgentInput = { threadId: id, runId: 'run-1', state: { unsafe: true }, context: [{ description: 'untrusted', value: 'injected' }], tools: [{ name: 'injected', description: '', parameters: {} }], messages: [{ id: 'old', role: 'assistant', content: 'Old response' }, { id: 'new', role: 'user', content: 'New question' }] }

test('new turns exclude history and client state; approvals carry no new messages', () => {
  expect(turnInput(input, id, model, 'medium')).toEqual({ threadId: id, runId: 'run-1', state: {}, context: [], tools: [], messages: [input.messages[1]], forwardedProps: { model_id: model.id, effort: 'medium' } })
  const resume = [{ interruptId: 'approval', status: 'resolved' as const, payload: { decisions: [{ type: 'approve' }] } }]
  expect(turnInput({ ...input, resume }, id, model, 'low')).toMatchObject({ messages: [], resume })
  expect(() => turnInput(input, id, model, 'none')).toThrow('supported reasoning effort')
  expect(() => turnInput(input, id, model, 'xhigh')).toThrow('supported reasoning effort')
  expect(() => turnInput({ ...input, messages: [{ id: 'large', role: 'user', content: 'x'.repeat(8001) }] }, id, model, 'low')).toThrow('8,000')
  const image = { type: 'image' as const, source: { type: 'data' as const, mimeType: 'image/png', value: 'aGVsbG8=' } }
  expect(() => turnInput({ ...input, messages: [{ id: 'images', role: 'user', content: [image] }] }, id, { ...model, vision: false }, 'low')).toThrow('vision model')
  expect(() => turnInput({ ...input, messages: [{ id: 'images', role: 'user', content: Array(5).fill(image) }] }, id, model, 'low')).toThrow('four images')
  expect(() => parseConversationDetails({ ...metadata, state: { messages: [{ role: 'invalid' }], pending_approvals: [] } })).toThrow()
})

let bundle: string
test.beforeAll(async () => {
  const result = await build({ entryPoints: ['tests/fixtures/assistant.tsx'], bundle: true, write: false, platform: 'browser', format: 'iife', jsx: 'automatic', define: { 'process.env.NODE_ENV': '"production"', 'process.env': '{}' }, logLevel: 'silent', loader: { '.css': 'empty' }, plugins: [{ name: 'fixture-platform', setup(builder) {
    builder.onResolve({ filter: /^(next\/link|next\/navigation|@\/components\/application\/providers)$/ }, args => ({ path: args.path, namespace: 'fixture-platform' }))
    builder.onLoad({ filter: /.*/, namespace: 'fixture-platform' }, args => ({ loader: 'tsx', resolveDir: process.cwd(), contents: args.path === 'next/link' ? `import {forwardRef} from 'react'; export default forwardRef(function Link({prefetch,replace,scroll,locale,...props},ref){return <a {...props} ref={ref}/>})` : args.path === 'next/navigation' ? `export function usePathname(){return '/app'}` : `export function useAccount(){return {status:'ready',signedIn:true,profile:null,name:'Test learner',signOut:async()=>{}}}; export function useTheme(){return {theme:'light',toggleTheme:()=>{}}}` }))
  } }] })
  bundle = result.outputFiles[0].text
})

async function fixture(page: Page) {
  await page.goto('/showcase?view=assistant')
  await expect(page.getByRole('heading', { name: 'An assistant, in good form.' })).toBeVisible()
  const styles = await page.locator('link[rel=stylesheet]').evaluateAll(nodes => nodes.map(node => (node as HTMLLinkElement).href))
  await page.route('**/__assistant_fixture__/bundle.js', route => route.fulfill({ contentType: 'application/javascript', body: bundle }))
  await page.route('**/__assistant_fixture__', route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><html lang="en"><head>${styles.map(href => `<link rel="stylesheet" href="${href}">`).join('')}</head><body><div id="fixture"></div><script src="/__assistant_fixture__/bundle.js"></script></body></html>` }))
  await page.goto('/__assistant_fixture__')
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
  await page.route('**/api/v1/assistant**', async route => {
    const request = route.request(), url = new URL(request.url())
    expect(request.headers().authorization).toBe('Bearer test-only-bearer')
    if (url.pathname.endsWith('/models')) return route.fulfill({ json: [model, { ...model, id: 'text-model', name: 'Text model', vision: false }] })
    if (url.pathname.endsWith('/conversations') && request.method() === 'GET') return route.fulfill({ json: { conversations: [metadata], next_cursor: url.searchParams.has('cursor') ? null : 'older-page' } })
    if (url.pathname.endsWith('/conversations') && request.method() === 'POST') return route.fulfill({ status: 201, json: { ...metadata, id: secondId, title: request.postDataJSON().title } })
    if (url.pathname.includes('/conversations/')) return route.fulfill({ json: { ...metadata, id: url.pathname.split('/').at(-1), state: options.pending ? { messages: [...state.messages, { id: 'pending-assistant', role: 'assistant', content: '', toolCalls: [{ id: 'tool-1', type: 'function', function: { name: 'create_node', arguments: '{"name":"New deck"}' } }] }], pending_approvals: [{ interrupt_id: 'interrupt-1', action_requests: [{ name: 'create_node', args: { name: 'New deck' } }] }] } : { ...state, messages: options.history ?? state.messages } } })
    expect(url.pathname).toBe('/api/v1/assistant:run')
    expect(request.method()).toBe('POST')
    const input = request.postDataJSON() as RunAgentInput
    requests.push(input)
    if (options.error) return route.fulfill({ status: 409, json: { error: 'conversation_busy' } })
    return route.fulfill({ contentType: 'text/event-stream', body: events(input.runId, options.answer, options.reasoning) })
  })
  return requests
}

test('showcase exercises reasoning, models, attachments, history and approval', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/showcase?view=assistant')
  await expect(page.locator('.ai-message-user')).toHaveCount(1)
  await expect(page.locator('.ai-message-content').first()).toHaveCSS('border-radius', '0px')
  await page.locator('.ai-reasoning summary').click()
  await expect(page.getByText(/A short illustrative reasoning summary/)).toBeVisible()
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

test('live panel sends a bounded new turn, streams, reopens history and restores focus', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const requests = await mockApi(page)
  await fixture(page)
  const launcher = page.getByRole('button', { name: 'Open PycilAI' })
  await launcher.click()
  await page.getByLabel('Message PycilAI').fill('Please explain discovery')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.ai-message-assistant')).toContainText('A streamed answer.')
  await page.locator('.ai-reasoning summary').click()
  await expect(page.locator('.ai-reasoning-body strong')).toHaveText('Considering car wash logistics')
  await expect(page.locator('.ai-reasoning-body p')).toHaveCount(2)
  await expect(page.locator('.ai-reasoning-body')).not.toContainText('**')
  const reasoningMarkdown = page.locator('.ai-reasoning-body .ai-markdown')
  await expect(reasoningMarkdown).toHaveCSS('white-space', 'normal')
  const paragraphGap = await reasoningMarkdown.locator('p').evaluateAll(nodes => nodes[1].getBoundingClientRect().top - nodes[0].getBoundingClientRect().bottom)
  expect(paragraphGap).toBeCloseTo(12, 0)
  expect(requests[0]).toMatchObject({ threadId: secondId, messages: [{ role: 'user', content: 'Please explain discovery' }], state: {}, tools: [], context: [], forwardedProps: { model_id: model.id, effort: 'medium' } })
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
  await page.getByLabel('Message PycilAI').fill('Follow up')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect.poll(() => requests.length).toBe(2)
  expect(requests[1].messages).toHaveLength(1)
  expect(requests[1].messages[0]).toMatchObject({ content: 'Follow up' })
  await page.keyboard.press('Escape')
  await expect(launcher).toBeFocused()
  expect(errors).toEqual([])
})

test('persisted approvals resume with matching interrupt and no transcript', async ({ page }) => {
  const requests = await mockApi(page, { pending: true })
  await fixture(page)
  await page.getByRole('button', { name: 'Open PycilAI' }).click()
  await page.getByRole('button', { name: 'Conversation history' }).click()
  await page.getByRole('button', { name: /^Discover or invent/ }).click()
  await page.getByRole('button', { name: 'Reject', exact: true }).click()
  await expect.poll(() => requests.length).toBe(1)
  expect(requests[0]).toMatchObject({ threadId: id, messages: [], resume: [{ interruptId: 'interrupt-1', status: 'resolved', payload: { decisions: [{ type: 'reject' }] } }] })
})

test('multi-step tools and reasoning use the available width without empty copy rows', async ({ page }) => {
  const history: RunAgentInput['messages'] = [{ id: 'request', role: 'user', content: 'Read my library before writing the essay.' }, { id: 'thinking', role: 'reasoning', content: 'First inspect the available folders.' }]
  for (const [index, name] of ['search_nodes', 'list_nodes', 'list_nodes'].entries()) {
    history.push(
      { id: `step-${index}`, role: 'assistant', content: '', toolCalls: [{ id: `call-${index}`, type: 'function', function: { name, arguments: '{"query":"Messi vs Ronaldo"}' } }] },
      { id: `result-${index}`, role: 'tool', toolCallId: `call-${index}`, content: '{"nodes":[]}' },
    )
  }
  history.push({ id: 'answer', role: 'assistant', content: 'The folder is empty. I can write the essay here.' })
  await mockApi(page, { history })
  await fixture(page)
  await page.getByRole('button', { name: 'Open PycilAI' }).click()
  await page.getByRole('button', { name: 'Conversation history' }).click()
  await page.getByRole('button', { name: /^Discover or invent/ }).click()
  await expect(page.locator('.ai-tool')).toHaveCount(3)
  await expect(page.getByRole('button', { name: 'Copy response' })).toHaveCount(1)
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
    await page.locator('.ai-tool summary').first().click()
    await expect(page.locator('.ai-tool-body').first()).toContainText('Messi vs Ronaldo')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.locator('.ai-tool summary').first().click()
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
  await page.getByRole('button', { name: 'Open PycilAI' }).click()
  await page.getByLabel('Message PycilAI').fill('Explain the integral')
  await page.getByRole('button', { name: 'Send message' }).click()
  await page.locator('.ai-reasoning summary').click()
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
  await page.getByRole('button', { name: 'Open PycilAI' }).click()
  await page.getByLabel('Message PycilAI').fill('A question')
  await page.getByRole('button', { name: 'Send message' }).click()
  await expect(page.locator('.ai-error')).toContainText('conversation is busy')
  expect(requests).toHaveLength(1)
})

test('assistant layouts stay inside desktop/mobile light/dark viewports', async ({ page }) => {
  mkdirSync('../../.impeccable/review/assistant', { recursive: true })
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
      await page.screenshot({ path: `../../.impeccable/review/assistant/showcase-${width}-${theme}.png`, fullPage: true })
    }
    await mockApi(page)
    await fixture(page)
    await page.getByRole('button', { name: 'Open PycilAI' }).click()
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
    await page.screenshot({ path: `../../.impeccable/review/assistant/panel-${width}.png` })
    await page.getByRole('button', { name: 'Close PycilAI' }).click()
  }
})
