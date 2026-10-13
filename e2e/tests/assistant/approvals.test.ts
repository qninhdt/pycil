import { randomUUID } from 'node:crypto'
import { test, expect } from '../../fixtures/index.ts'
import { openAssistant, sendMessage, completion, completedResponse } from '../../support/assistant.ts'

for (const approved of [true, false]) {
  test(`a staged deck creation survives reload and ${approved ? 'approval commits it' : 'rejection leaves the library unchanged'}`, async ({ actor, data, vocabulary, scenarios }) => {
    const id = randomUUID()
    const name = `Finance ${id.slice(0, 8)}`
    await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [
      { status: 200, chunks: completion('', { tool: { name: 'create_node', args: { type: 'deck', name, parent_id: actor.account.personal_node_id, sense_ids: [vocabulary.bankFinancial.sense_id] } } }) },
      ...(approved ? [{ status: 200, chunks: completion('Your finance deck is ready.'), requiredInput: [name, 'create_node'] }] : []),
    ] })
    await actor.page.goto(`/app/personal/${actor.account.personal_node_id}`)
    await openAssistant(actor.page)
    await sendMessage(actor.page, `Create a finance deck called ${name}. Request ${id}.`)
    await expect(actor.page.getByRole('button', { name: 'Approve changes', exact: true })).toBeVisible()
    expect(await actor.api.call(`nodes/${actor.account.personal_node_id}:search?q=${encodeURIComponent(name)}`)).toMatchObject({ nodes: [] })
    await actor.page.reload()
    await openAssistant(actor.page)
    await expect(actor.page.getByRole('button', { name: 'Approve changes', exact: true })).toBeVisible()
    await actor.page.getByRole('button', { name: approved ? 'Approve changes' : 'Reject', exact: true }).click()
    if (approved) {
      await completedResponse(actor.page, 'Your finance deck is ready.')
      const found = await actor.api.call<{ nodes: { id: string; name: string }[] }>(`nodes/${actor.account.personal_node_id}:search?q=${encodeURIComponent(name)}`)
      expect(found.nodes).toHaveLength(1)
      data.track(found.nodes[0].id)
      await actor.page.getByRole('button', { name: 'Close PycilAI', exact: true }).click()
      await expect(actor.page.getByRole('link').filter({ hasText: name })).toBeVisible()
    } else {
      await expect(actor.page.getByRole('button', { name: 'Approve changes', exact: true })).not.toBeVisible()
      await expect(actor.page.getByRole('button', { name: 'Send message', exact: true })).toBeVisible()
      expect(await actor.api.call(`nodes/${actor.account.personal_node_id}:search?q=${encodeURIComponent(name)}`)).toMatchObject({ nodes: [] })
    }
  })
}

test('auto approval commits a normal deck tool write without showing an approval prompt', async ({ actor, data, vocabulary, scenarios }) => {
  const id = randomUUID()
  const name = `Automatic finance ${id.slice(0, 8)}`
  await actor.api.call('me/settings', 'PATCH', { assistant: { auto_approve: true } })
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [
    { status: 200, chunks: completion('', { tool: { name: 'create_node', args: { type: 'deck', name, parent_id: actor.account.personal_node_id, sense_ids: [vocabulary.bankFinancial.sense_id] } } }) },
    { status: 200, chunks: completion('Your automatic deck is ready.'), requiredInput: [name, 'create_node'] },
  ] })
  await actor.page.goto('/app/personal')
  await openAssistant(actor.page)
  await sendMessage(actor.page, `Create ${name}. ${id}`)
  await completedResponse(actor.page, 'Your automatic deck is ready.')
  await expect(actor.page.getByRole('button', { name: 'Approve changes', exact: true })).not.toBeVisible()
  const found = await actor.api.call<{ nodes: { id: string }[] }>(`nodes/${actor.account.personal_node_id}:search?q=${encodeURIComponent(name)}`)
  expect(found.nodes).toHaveLength(1)
  data.track(found.nodes[0].id)
})

test('auto approval cannot publish a deck without explicit publication consent', async ({ actor, data, vocabulary, scenarios, guest }) => {
  const id = randomUUID()
  const deck = await data.create({ name: 'Consent required finance', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await actor.api.call('me/settings', 'PATCH', { assistant: { auto_approve: true } })
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [
    { status: 200, chunks: completion('', { tool: { name: 'move_nodes', args: { node_ids: [deck.id], parent_id: actor.account.published_node_id } } }) },
    { status: 200, chunks: completion('Publication requires your consent.'), requiredInput: ['publication_confirmation_required'] },
  ] })
  await actor.page.goto(`/app/personal/${deck.id}`)
  await openAssistant(actor.page)
  await sendMessage(actor.page, `Publish this finance deck. ${id}`)
  await completedResponse(actor.page, 'Publication requires your consent.')
  expect(await actor.api.call(`nodes/${deck.id}`)).toMatchObject({ space: 'personal' })
  await guest.goto(`/u/${actor.account.id}/${deck.id}`)
  await expect(guest.getByRole('heading', { level: 1 })).not.toContainText(deck.name)
  await actor.page.getByRole('button', { name: 'Close PycilAI', exact: true }).click()
  await actor.page.getByRole('button', { name: `Settings for ${deck.name}`, exact: true }).click()
  await actor.page.getByRole('menuitem', { name: 'Publish', exact: true }).click()
  await actor.page.getByRole('alertdialog').getByRole('button', { name: 'Publish', exact: true }).click()
  await expect(actor.page).toHaveURL(new RegExp(`/app/published/${deck.id}$`))
  await guest.reload()
  await expect(guest.getByRole('heading', { level: 1 })).toContainText(deck.name)
})
