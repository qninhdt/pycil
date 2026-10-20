import { randomUUID } from 'node:crypto'
import { test, expect } from '../../fixtures/index.ts'
import { openAssistant, sendMessage, completion, completedResponse } from '../../support/assistant.ts'
import { apiURL } from '../../support/environment.ts'

test('current view follows navigation and a read tool returns real authorized deck content', async ({ user, data, request, vocabulary, scenarios }) => {
  const deck = await data.create({ name: 'Finance context', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  const id = randomUUID()
  await scenarios.register({ id, path: '/chat/completions', contains: id, responses: [
    { status: 200, chunks: completion('', { tool: { name: 'read_library', args: { node_id: deck.id, view: 'content' } } }), requiredInput: [deck.id, `/app/personal/${deck.id}`] },
    { status: 200, chunks: completion('This deck contains the financial meaning of bank.'), requiredInput: [deck.name, 'an institution where people keep and borrow money'] },
  ] })
  await user.page.goto(`/app/personal/${deck.id}`)
  await openAssistant(user.page)
  const domainReads: string[] = []
  user.page.on('request', request => { if (request.url().includes(`/v1/nodes/${deck.id}`)) domainReads.push(request.url()) })
  await sendMessage(user.page, `Read the content of my current deck. Request ${id}.`)
  await completedResponse(user.page, 'This deck contains the financial meaning of bank.')
  expect(domainReads).toEqual([])
  expect([401, 404]).toContain((await request.get(`${apiURL}/v1/nodes/${deck.id}`)).status())
  const history = await user.api.call<{ conversations: { id: string }[] }>('assistant/conversations')
  expect([401, 404]).toContain((await request.get(`${apiURL}/v1/assistant/conversations/${history.conversations[0].id}`)).status())
})
