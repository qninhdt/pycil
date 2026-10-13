import { expect, type Page } from '@playwright/test'
import { randomUUID } from 'node:crypto'

export async function openAssistant(page: Page) {
  const panel = page.getByRole('complementary', { name: 'PycilAI', exact: true })
  const launcher = page.getByRole('button', { name: 'Open PycilAI', exact: true })
  await expect.poll(async () => await panel.isVisible() || await launcher.isVisible()).toBe(true)
  if (!await panel.isVisible()) await launcher.click()
  await expect(page.getByRole('textbox', { name: 'Message PycilAI', exact: true })).toBeVisible()
}

export async function sendMessage(page: Page, message: string) {
  await page.getByRole('textbox', { name: 'Message PycilAI', exact: true }).fill(message)
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
}

export async function completedResponse(page: Page, text: string) {
  await expect(page.locator('.ai-panel').getByText(text, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Send message', exact: true })).toBeVisible()
}

export function completion(text: string, options: { tool?: { name: string; args: unknown }; reasoning?: string } = {}) {
  const id = `chatcmpl-${randomUUID()}`
  const chunk = (delta: unknown, finish_reason: string | null = null) => ({ id, object: 'chat.completion.chunk', created: 1, model: 'openai/gpt-6-luna', choices: [{ index: 0, delta, finish_reason }] })
  const chunks: unknown[] = [chunk({ role: 'assistant', content: '' })]
  if (options.reasoning) chunks.push(chunk({ reasoning: options.reasoning }))
  if (text) chunks.push(chunk({ content: text }))
  if (options.tool) chunks.push(chunk({ tool_calls: [{ index: 0, id: `call_${randomUUID()}`, type: 'function', function: { name: options.tool.name, arguments: JSON.stringify(options.tool.args) } }] }))
  chunks.push(chunk({}, options.tool ? 'tool_calls' : 'stop'))
  chunks.push({ id, object: 'chat.completion.chunk', created: 1, model: 'openai/gpt-6-luna', choices: [], usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 } })
  return chunks
}
