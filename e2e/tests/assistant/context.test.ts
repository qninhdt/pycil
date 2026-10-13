import { randomUUID } from 'node:crypto'
import { test, expect } from '../../fixtures/index.ts'
import { openAssistant, sendMessage, completion, completedResponse } from '../../support/assistant.ts'

test('current view follows navigation and a read tool returns real authorized deck content', async ({ actor, data, secondary, vocabulary, scenarios }) => {
  const deck = await data.create({ name: 'Finance context', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  const id = randomUUID()
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [
    { status: 200, chunks: completion('', { tool: { name: 'read_library', args: { node_id: deck.id, view: 'content' } } }), requiredInput: [deck.id, `/app/personal/${deck.id}`] },
    { status: 200, chunks: completion('This deck contains the financial meaning of bank.'), requiredInput: [deck.name, 'an institution where people keep and borrow money'] },
  ] })
  await actor.page.goto(`/app/personal/${deck.id}`)
  await openAssistant(actor.page)
  const domainReads: string[] = []
  actor.page.on('request', request => { if (request.url().includes(`/v1/nodes/${deck.id}`)) domainReads.push(request.url()) })
  await sendMessage(actor.page, `Read the content of my current deck. Request ${id}.`)
  await completedResponse(actor.page, 'This deck contains the financial meaning of bank.')
  expect(domainReads).toEqual([])
  await secondary.api.call(`nodes/${deck.id}`, 'GET', undefined, 404)
  const history = await actor.api.call<{ conversations: { id: string }[] }>('assistant/conversations')
  await secondary.api.call(`assistant/conversations/${history.conversations[0].id}`, 'GET', undefined, 404)
})
