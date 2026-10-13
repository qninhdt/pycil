import { randomUUID } from 'node:crypto'
import { test, expect } from '../../fixtures/index.ts'
import { openAssistant, sendMessage, completion, completedResponse } from '../../support/assistant.ts'

test('partial response is visible before completion and persisted follow-up survives reload', async ({ actor, scenarios }) => {
  const id = randomUUID()
  const prompt = `Explain the financial meaning of bank for conversation ${id}.`
  const answer = 'A bank keeps savings and lends money.'
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [
    { status: 200, chunks: completion(answer, { reasoning: 'I will explain the financial meaning.' }), pauseAfter: 3 },
    { status: 200, chunks: completion('For example, she deposited her savings at the bank.'), requiredInput: [answer] },
  ] })
  await openAssistant(actor.page)
  await sendMessage(actor.page, prompt)
  await expect(actor.page.locator('.ai-panel').getByText(answer, { exact: true })).toBeVisible()
  await expect(actor.page.getByRole('button', { name: 'Stop response', exact: true })).toBeVisible()
  await scenarios.release(id)
  await completedResponse(actor.page, answer)
  await sendMessage(actor.page, 'Give me an example of that meaning.')
  await completedResponse(actor.page, 'For example, she deposited her savings at the bank.')
  const list = await actor.api.call<{ conversations: { id: string }[] }>('assistant/conversations')
  expect(list.conversations).toHaveLength(1)
  const conversationId = list.conversations[0].id
  const details = await actor.api.call<{ state: { messages: unknown[] } }>(`assistant/conversations/${conversationId}`)
  expect(JSON.stringify(details.state.messages)).toContain(answer)
  await actor.page.reload()
  await openAssistant(actor.page)
  await expect(actor.page.locator('.ai-panel').getByText(answer, { exact: true })).toBeVisible()
  await expect(actor.page.locator('.ai-panel').getByText('For example, she deposited her savings at the bank.', { exact: true })).toBeVisible()
})

test('history loads older conversations and deletion removes the selected conversation only', async ({ actor }) => {
  const created: { id: string; title: string }[] = []
  for (let index = 0; index < 26; index++) {
    created.push(await actor.api.call('assistant/conversations', 'POST', { title: `Reading conversation ${index + 1}` }, 201))
  }
  await actor.page.goto('/app')
  await openAssistant(actor.page)
  await actor.page.getByRole('button', { name: 'Conversation history', exact: true }).click()
  await actor.page.getByRole('button', { name: 'Load older conversations', exact: true }).click()
  const oldest = created[0]
  await expect(actor.page.getByRole('button', { name: `Delete conversation ${oldest.title}`, exact: true })).toBeVisible()
  await actor.page.getByRole('button', { name: `Delete conversation ${oldest.title}`, exact: true }).click()
  await actor.page.getByRole('alertdialog').getByRole('button', { name: 'Delete conversation', exact: true }).click()
  await expect(actor.page.getByRole('button', { name: `Delete conversation ${oldest.title}`, exact: true })).not.toBeVisible()
  await actor.api.call(`assistant/conversations/${oldest.id}`, 'GET', undefined, 404)
  expect(await actor.api.call(`assistant/conversations/${created[1].id}`)).toMatchObject({ id: created[1].id })
})

test('a valid image reaches the native model and checkpoint while an invalid upload stays out of the composer', async ({ actor, scenarios }) => {
  const id = randomUUID()
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [{ status: 200, chunks: completion('The attached image arrived with your question.'), requiredInput: ['data:image/png;base64,'] }] })
  await actor.page.goto('/app')
  await openAssistant(actor.page)
  const invalidChooser = actor.page.waitForEvent('filechooser')
  await actor.page.getByRole('button', { name: 'Attach images', exact: true }).click()
  await (await invalidChooser).setFiles({ name: 'invalid.txt', mimeType: 'text/plain', buffer: Buffer.from('This is not an image.') })
  await expect(actor.page.getByText(/Only.*image|supported image|PNG.*JPEG/i).first()).toBeVisible()
  const validChooser = actor.page.waitForEvent('filechooser')
  await actor.page.getByRole('button', { name: 'Attach images', exact: true }).click()
  await (await validChooser).setFiles({ name: 'reading.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6SAAAAABJRU5ErkJggg==', 'base64') })
  await sendMessage(actor.page, `Describe my reading image. ${id}`)
  await completedResponse(actor.page, 'The attached image arrived with your question.')
  const history = await actor.api.call<{ conversations: { id: string }[] }>('assistant/conversations')
  const details = await actor.api.call<{ state: { messages: unknown[] } }>(`assistant/conversations/${history.conversations[0].id}`)
  expect(details.state.messages).toEqual(expect.arrayContaining([expect.objectContaining({
    role: 'user', content: expect.arrayContaining([expect.objectContaining({
      type: 'image', source: expect.objectContaining({ type: 'data', mimeType: 'image/png', value: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6SAAAAABJRU5ErkJggg==' }),
    })]),
  })]))
})
