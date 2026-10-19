import { randomUUID } from 'node:crypto'
import { test, expect } from '../../fixtures/index.ts'
import { openAssistant, sendMessage, completion, completedResponse } from '../../support/assistant.ts'

test('partial response is visible before completion and persisted follow-up survives reload', async ({ user, scenarios }) => {
  const id = randomUUID()
  const prompt = `Explain the financial meaning of bank for conversation ${id}.`
  const answer = 'A bank keeps savings and lends money.'
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [
    { status: 200, chunks: completion(answer, { reasoning: 'I will explain the financial meaning.' }), pauseAfter: 3 },
    { status: 200, chunks: completion('For example, she deposited her savings at the bank.'), requiredInput: [answer] },
  ] })
  await openAssistant(user.page)
  await sendMessage(user.page, prompt)
  await expect(user.page.locator('.ai-panel').getByText(answer, { exact: true })).toBeVisible()
  await expect(user.page.getByRole('button', { name: 'Stop response', exact: true })).toBeVisible()
  await scenarios.release(id)
  await completedResponse(user.page, answer)
  await sendMessage(user.page, 'Give me an example of that meaning.')
  await completedResponse(user.page, 'For example, she deposited her savings at the bank.')
  const list = await user.api.call<{ conversations: { id: string }[] }>('assistant/conversations')
  expect(list.conversations).toHaveLength(1)
  const conversationId = list.conversations[0].id
  const details = await user.api.call<{ state: { messages: unknown[] } }>(`assistant/conversations/${conversationId}`)
  expect(JSON.stringify(details.state.messages)).toContain(answer)
  await user.page.reload()
  await openAssistant(user.page)
  await expect(user.page.locator('.ai-panel').getByText(answer, { exact: true })).toBeVisible()
  await expect(user.page.locator('.ai-panel').getByText('For example, she deposited her savings at the bank.', { exact: true })).toBeVisible()
})

test('history loads older conversations and deletion removes the selected conversation only', async ({ user }) => {
  const created = await Promise.all(
    Array.from({ length: 26 }, (_, index) =>
      user.api.call<{ id: string; title: string; updated_at: string }>('assistant/conversations', 'POST', { title: `Reading conversation ${index + 1}` }, 201)
    )
  )
  created.sort((a, b) => a.updated_at.localeCompare(b.updated_at))
  await user.page.goto('/app')
  await openAssistant(user.page)
  await user.page.getByRole('button', { name: 'Conversation history', exact: true }).click()
  await user.page.getByRole('button', { name: 'Load older conversations', exact: true }).click()
  const oldest = created[0]
  await expect(user.page.getByRole('button', { name: `Delete conversation ${oldest.title}`, exact: true })).toBeVisible()
  await user.page.getByRole('button', { name: `Delete conversation ${oldest.title}`, exact: true }).click()
  await user.page.getByRole('alertdialog').getByRole('button', { name: 'Delete conversation', exact: true }).click()
  await expect(user.page.getByRole('alertdialog')).not.toBeVisible()
  await expect(user.page.getByRole('button', { name: `Delete conversation ${oldest.title}`, exact: true })).toHaveCount(0)
  await user.api.call(`assistant/conversations/${oldest.id}`, 'GET', undefined, 404)
  expect(await user.api.call(`assistant/conversations/${created[1].id}`)).toMatchObject({ id: created[1].id })
})

test('a valid image reaches the native model and checkpoint while an invalid upload stays out of the composer', async ({ user, scenarios }) => {
  const id = randomUUID()
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [{ status: 200, chunks: completion('The attached image arrived with your question.'), requiredInput: ['data:image/png;base64,'] }] })
  await user.page.goto('/app')
  await openAssistant(user.page)
  const invalidChooser = user.page.waitForEvent('filechooser')
  await user.page.getByRole('button', { name: 'Attach images', exact: true }).click()
  await (await invalidChooser).setFiles({ name: 'invalid.txt', mimeType: 'text/plain', buffer: Buffer.from('This is not an image.') })
  await expect(user.page.getByText(/Only.*image|supported image|PNG.*JPEG/i).first()).toBeVisible()
  const validChooser = user.page.waitForEvent('filechooser')
  await user.page.getByRole('button', { name: 'Attach images', exact: true }).click()
  await (await validChooser).setFiles({ name: 'reading.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6SAAAAABJRU5ErkJggg==', 'base64') })
  await sendMessage(user.page, `Describe my reading image. ${id}`)
  await completedResponse(user.page, 'The attached image arrived with your question.')
  const history = await user.api.call<{ conversations: { id: string }[] }>('assistant/conversations')
  const details = await user.api.call<{ state: { messages: unknown[] } }>(`assistant/conversations/${history.conversations[0].id}`)
  expect(details.state.messages).toEqual(expect.arrayContaining([expect.objectContaining({
    role: 'user', content: expect.arrayContaining([expect.objectContaining({
      type: 'image', source: expect.objectContaining({ type: 'data', mimeType: 'image/png', value: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6SAAAAABJRU5ErkJggg==' }),
    })]),
  })]))
})
