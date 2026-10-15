import { randomUUID } from 'node:crypto'
import { test, expect } from '../../fixtures/index.ts'
import { openAssistant, sendMessage, completion, completedResponse } from '../../support/assistant.ts'

test('a provider failure leaves the composer usable for the next real turn', async ({ user, scenarios }) => {
  const id = randomUUID()
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [
    { status: 503, body: { error: { type: 'server_error', message: 'Provider unavailable for this scenario' } } },
    { status: 200, chunks: completion('The financial meaning describes an institution for money.') },
  ] })
  await openAssistant(user.page)
  await sendMessage(user.page, `Explain the financial meaning. Request ${id}.`)
  await expect(user.page.locator('.ai-panel').getByRole('alert').filter({ hasText: /^The response failed/ })).toBeVisible()
  await expect(user.page.getByRole('button', { name: 'Send message', exact: true })).toBeVisible()
  await sendMessage(user.page, 'Try explaining it again.')
  await completedResponse(user.page, 'The financial meaning describes an institution for money.')
})

test('cancelling a partial stream permits another turn without an orphan provider stream', async ({ user, scenarios }) => {
  const id = randomUUID()
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [
    { status: 200, chunks: completion('A bank is a financial institution.'), pauseAfter: 2 },
    { status: 200, chunks: completion('A river bank is the ground beside a river.') },
  ] })
  await openAssistant(user.page)
  await sendMessage(user.page, `Compare two meanings of bank. Request ${id}.`)
  await expect(user.page.locator('.ai-panel').getByText('A bank is a financial institution.', { exact: true })).toBeVisible()
  await user.page.getByRole('button', { name: 'Stop response', exact: true }).click()
  await scenarios.settled(id)
  await expect(user.page.getByRole('button', { name: 'Send message', exact: true })).toBeVisible()
  await sendMessage(user.page, 'Now describe the river meaning.')
  await completedResponse(user.page, 'A river bank is the ground beside a river.')
})

test('a tool authorization error is visible and does not prevent a subsequent turn', async ({ user, secondary, vocabulary, scenarios }) => {
  const privateDeck = await secondary.api.call<{ id: string }>('nodes', 'POST', { name: 'Another account private deck', type: 'deck', parent_id: secondary.account.personal_node_id, sense_ids: [vocabulary.bankFinancial.sense_id] }, 201)
  const id = randomUUID()
  try {
    await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [
      { status: 200, chunks: completion('', { tool: { name: 'read_library', args: { node_id: privateDeck.id } } }) },
      { status: 200, chunks: completion('That private deck is unavailable to this account.'), requiredInput: ['read_library'] },
      { status: 200, chunks: completion('We can continue with your own vocabulary.') },
    ] })
    await user.page.goto('/app')
    await openAssistant(user.page)
    await sendMessage(user.page, `Read deck ${privateDeck.id}. ${id}`)
    await completedResponse(user.page, 'That private deck is unavailable to this account.')
    const history = await user.api.call<{ conversations: { id: string }[] }>('assistant/conversations')
    const details = await user.api.call<{ state: { messages: unknown[] } }>(`assistant/conversations/${history.conversations[0].id}`)
    expect(JSON.stringify(details.state.messages)).not.toContain('an institution where people keep and borrow money')
    await sendMessage(user.page, 'Continue using my own words.')
    await completedResponse(user.page, 'We can continue with your own vocabulary.')
  } finally { await secondary.api.call(`nodes/${privateDeck.id}`, 'DELETE', undefined, [204, 404]) }
})

test('a deleted remembered conversation does not prevent starting another conversation', async ({ user, scenarios }) => {
  const id = randomUUID()
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [
    { status: 200, chunks: completion('The first conversation is saved.') },
    { status: 200, chunks: completion('A new conversation works after deletion.') },
  ] })
  await user.page.goto('/app')
  await openAssistant(user.page)
  await sendMessage(user.page, `Start a first conversation. ${id}`)
  await completedResponse(user.page, 'The first conversation is saved.')
  const history = await user.api.call<{ conversations: { id: string }[] }>('assistant/conversations')
  await user.api.call(`assistant/conversations/${history.conversations[0].id}`, 'DELETE', undefined, 204)
  await user.page.reload()
  await openAssistant(user.page)
  await sendMessage(user.page, `Start a new conversation. ${id}`)
  await completedResponse(user.page, 'A new conversation works after deletion.')
  const remaining = await user.api.call<{ conversations: { id: string }[] }>('assistant/conversations')
  expect(remaining.conversations).toHaveLength(1)
  expect(remaining.conversations[0].id).not.toBe(history.conversations[0].id)
})
