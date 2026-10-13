import { randomUUID } from 'node:crypto'
import { test, expect } from '../../fixtures/index.ts'
import { openAssistant, sendMessage, completion, completedResponse } from '../../support/assistant.ts'

test('a completed turn consumes the actor allowance and another account cannot read its checkpoint', async ({ actor, secondary, scenarios }) => {
  const id = randomUUID()
  const before = await actor.api.call<{ used_units: number }>('me/usage')
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [{ status: 200, chunks: completion('Your own account keeps this response.') }] })
  await actor.page.goto('/app')
  await openAssistant(actor.page)
  await sendMessage(actor.page, `Explain saving a word. ${id}`)
  await completedResponse(actor.page, 'Your own account keeps this response.')
  await expect.poll(async () => (await actor.api.call<{ used_units: number }>('me/usage')).used_units).toBeGreaterThan(before.used_units)
  const history = await actor.api.call<{ conversations: { id: string }[] }>('assistant/conversations')
  expect(history.conversations).toHaveLength(1)
  await secondary.api.call(`assistant/conversations/${history.conversations[0].id}`, 'GET', undefined, [403, 404])
})

test('an exhausted allowance rejects a browser turn before reaching the model', async ({ actor, data }) => {
  await data.prepareActor({ exhausted: true })
  await actor.page.goto('/app')
  await openAssistant(actor.page)
  const response = actor.page.waitForResponse(response => response.url().endsWith('/assistant:run') && response.request().method() === 'POST')
  await sendMessage(actor.page, 'Explain a word without an available allowance.')
  expect((await response).status()).toBe(403)
  await expect(actor.page.getByText('Your AI allowance is exhausted. Check the reset date before starting another response.', { exact: true })).toBeVisible()
  await expect(actor.page.getByRole('button', { name: 'Send message', exact: true })).toBeVisible()
  expect(await actor.api.call('study/progress')).toMatchObject({ studied: 0 })
})

test('rejecting an already pending mutation remains possible after the allowance is exhausted', async ({ actor, data, scenarios }) => {
  const id = randomUUID()
  const name = 'A rejected exhausted mutation'
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [{ status: 200, chunks: completion('', { tool: { name: 'create_node', args: { type: 'deck', name, parent_id: actor.account.personal_node_id } } }) }] })
  await actor.page.goto('/app')
  await openAssistant(actor.page)
  await sendMessage(actor.page, `Create ${name}. ${id}`)
  await expect(actor.page.getByRole('button', { name: 'Approve changes', exact: true })).toBeVisible()
  await data.prepareActor({ exhausted: true })
  await actor.page.reload()
  await openAssistant(actor.page)
  await actor.page.getByRole('button', { name: 'Reject', exact: true }).click()
  await expect(actor.page.getByRole('button', { name: 'Approve changes', exact: true })).not.toBeVisible()
  expect(await actor.api.call(`nodes/${actor.account.personal_node_id}:search?q=${encodeURIComponent(name)}`)).toMatchObject({ nodes: [] })
})

for (const plan of ['free', 'pro'] as const) {
  test(`${plan} model and effort controls use the actual permitted catalog in a real turn`, async ({ actor, data, scenarios }) => {
    await data.prepareActor({ plan })
    const catalog = await actor.api.call<{ id: string; name: string; vision: boolean; efforts: string[] }[]>('assistant/models')
    expect(catalog.length).toBeGreaterThan(0)
    const selected = catalog.at(-1)!
    const effort = selected.efforts.at(-1)!
    const id = randomUUID()
    await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [{ status: 200, chunks: completion('The chosen model answered.'), requiredInput: [selected.id, `"effort":"${effort}"`] }] })
    await actor.page.goto('/app')
    await openAssistant(actor.page)
    await actor.page.getByRole('button', { name: 'Choose model', exact: true }).click()
    await actor.page.getByRole('button', { name: 'Select model', exact: true }).click()
    const options = actor.page.getByRole('menuitemradio')
    await expect(options).toHaveCount(catalog.length)
    await actor.page.getByRole('menuitemradio', { name: selected.name, exact: true }).click()
    await actor.page.getByRole('button', { name: 'Choose model', exact: true }).click()
    await actor.page.getByRole('button', { name: effort[0].toUpperCase() + effort.slice(1), exact: true }).click()
    await actor.page.keyboard.press('Escape')
    await expect(actor.page.getByRole('button', { name: 'Attach images', exact: true })).toBeEnabled({ enabled: selected.vision })
    await sendMessage(actor.page, `Use the selected model and effort. ${id}`)
    await completedResponse(actor.page, 'The chosen model answered.')
  })
}
