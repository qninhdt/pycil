import { randomUUID } from 'node:crypto'
import { test, expect } from '../../fixtures/index.ts'
import { openAssistant, sendMessage, completion, completedResponse } from '../../support/assistant.ts'
import { apiURL } from '../../support/environment.ts'

test('a completed turn consumes the user allowance and another account cannot read its checkpoint', async ({ user, request, scenarios }) => {
  const id = randomUUID()
  const before = await user.api.call<{ used_units: number }>('me/usage')
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [{ status: 200, chunks: completion('Your own account keeps this response.') }] })
  await user.page.goto('/app')
  await openAssistant(user.page)
  await sendMessage(user.page, `Explain saving a word. ${id}`)
  await completedResponse(user.page, 'Your own account keeps this response.')
  await expect.poll(async () => (await user.api.call<{ used_units: number }>('me/usage')).used_units).toBeGreaterThan(before.used_units)
  const history = await user.api.call<{ conversations: { id: string }[] }>('assistant/conversations')
  expect(history.conversations).toHaveLength(1)
  const response = await request.get(`${apiURL}/v1/assistant/conversations/${history.conversations[0].id}`)
  expect([401, 403, 404]).toContain(response.status())
})

test('an exhausted allowance rejects a browser turn before reaching the model', async ({ user, data }) => {
  await data.prepareUser({ exhausted: true })
  await user.page.goto('/app')
  await openAssistant(user.page)
  const response = user.page.waitForResponse(response => response.url().endsWith('/assistant:run') && response.request().method() === 'POST')
  await sendMessage(user.page, 'Explain a word without an available allowance.')
  expect((await response).status()).toBe(403)
  await expect(user.page.getByText('Your AI allowance is exhausted. Check the reset date before starting another response.', { exact: true })).toBeVisible()
  await expect(user.page.getByRole('button', { name: 'Send message', exact: true })).toBeVisible()
  expect(await user.api.call('study/progress')).toMatchObject({ studied: 0 })
})

test('rejecting an already pending mutation remains possible after the allowance is exhausted', async ({ user, data, scenarios }) => {
  const id = randomUUID()
  const name = 'A rejected exhausted mutation'
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [{ status: 200, chunks: completion('', { tool: { name: 'create_node', args: { type: 'deck', name, parent_id: user.account.personal_node_id } } }) }] })
  await user.page.goto('/app')
  await openAssistant(user.page)
  await sendMessage(user.page, `Create ${name}. ${id}`)
  await expect(user.page.getByRole('button', { name: 'Approve changes', exact: true })).toBeVisible()
  await data.prepareUser({ exhausted: true })
  await user.page.reload()
  await openAssistant(user.page)
  await user.page.getByRole('button', { name: 'Reject', exact: true }).click()
  await expect(user.page.getByRole('button', { name: 'Approve changes', exact: true })).not.toBeVisible()
  expect(await user.api.call(`nodes/${user.account.personal_node_id}:search?q=${encodeURIComponent(name)}`)).toMatchObject({ nodes: [] })
})

for (const plan of ['free', 'pro'] as const) {
  test(`${plan} model and effort controls use the actual permitted catalog in a real turn`, async ({ user, data, scenarios }) => {
    await data.prepareUser({ plan })
    const catalog = await user.api.call<{ id: string; name: string; vision: boolean; efforts: string[] }[]>('assistant/models')
    expect(catalog.length).toBeGreaterThan(0)
    const selected = catalog.at(-1)!
    const effort = selected.efforts.at(-1)!
    const id = randomUUID()
    await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [{ status: 200, chunks: completion('The chosen model answered.'), requiredInput: [selected.id, `"effort":"${effort}"`] }] })
    await user.page.goto('/app')
    await openAssistant(user.page)
    await user.page.getByRole('button', { name: 'Choose model', exact: true }).click()
    await user.page.getByRole('button', { name: 'Select model', exact: true }).click()
    const options = user.page.getByRole('menuitemradio')
    await expect(options).toHaveCount(catalog.length)
    await user.page.getByRole('menuitemradio', { name: selected.name, exact: true }).click()
    await user.page.getByRole('button', { name: 'Choose model', exact: true }).click()
    await user.page.getByRole('button', { name: effort[0].toUpperCase() + effort.slice(1), exact: true }).click()
    await user.page.keyboard.press('Escape')
    await expect(user.page.getByRole('button', { name: 'Attach images', exact: true })).toBeEnabled({ enabled: selected.vision })
    await sendMessage(user.page, `Use the selected model and effort. ${id}`)
    await completedResponse(user.page, 'The chosen model answered.')
  })
}
