import { randomUUID } from 'node:crypto'
import { structuredCompletion } from '../../support/model-provider.ts'
import { test, expect } from '../../fixtures/index.ts'
import { answerChoice, finishStudy, selectQuestions, startStudy } from '../../support/study.ts'

test('reload and pause retain an answered question without recording progress', async ({ user, data, vocabulary }) => {
  await selectQuestions(user)
  await user.api.call('me/settings', 'PATCH', { learning: { questions_per_sense: 2 } })
  const deck = await data.create({ name: 'Resumable finance', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await startStudy(user.page, deck.id)
  await user.page.reload()
  await expect(user.page.getByRole('button').filter({ hasText: 'bank' })).toBeVisible()
  await answerChoice(user.page, 'bank')
  await user.page.getByRole('button', { name: 'Exit learning mode', exact: true }).click()
  await user.page.getByRole('button', { name: 'Pause & exit', exact: true }).click()
  await expect(user.page).toHaveURL(new RegExp(`/app/personal/${deck.id}$`))
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 0 })
  await user.page.goto(`/app/learn?node=${deck.id}&selection=new`)
  await expect(user.page.getByText('That fits.', { exact: true })).toBeVisible()
  await user.page.getByRole('button', { name: /^Continue/ }).click()
  await answerChoice(user.page, 'bank')
  await finishStudy(user.page)
})

test('retrying after losing the committed submission response keeps one activity event', async ({ user, data, vocabulary }) => {
  await selectQuestions(user)
  const deck = await data.create({ name: 'Replay finance', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await startStudy(user.page, deck.id)
  await answerChoice(user.page, 'bank')
  const keys: string[] = []
  let lost = false
  await user.page.route('**/v1/study:submitResults', async route => {
    keys.push(route.request().headers()['idempotency-key'])
    if (!lost) {
      const committed = await route.fetch()
      expect(committed.status()).toBe(200)
      lost = true
      await route.abort('connectionreset')
    } else await route.continue()
  })
  await user.page.getByRole('button', { name: /^Continue/ }).click()
  await expect(user.page.getByRole('button', { name: 'Retry the same submission', exact: true })).toBeVisible()
  expect(await user.api.call('study/activity')).toMatchObject({ applied_events: 1 })
  await user.page.getByRole('button', { name: 'Retry the same submission', exact: true }).click()
  await expect(user.page.getByRole('heading', { name: 'Session complete', exact: true })).toBeVisible()
  expect(keys).toHaveLength(2)
  expect(keys[1]).toBe(keys[0])
  expect(await user.api.call('study/activity')).toMatchObject({ applied_events: 1 })
})

test('early finish saves the completed answer without inventing an answer for the remaining question', async ({ user, data, vocabulary }) => {
  await selectQuestions(user)
  await user.api.call('me/settings', 'PATCH', { learning: { questions_per_sense: 2 } })
  const deck = await data.create({ name: 'Early completion', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await startStudy(user.page, deck.id)
  await answerChoice(user.page, 'bank')
  await user.page.getByRole('button', { name: 'Exit learning mode', exact: true }).click()
  await user.page.getByRole('button', { name: 'Finish & save', exact: true }).click()
  await expect(user.page.getByRole('heading', { name: 'Session complete', exact: true })).toBeVisible()
  expect(await user.api.call('study/activity')).toMatchObject({ applied_events: 1 })
})

test('another tab cannot overwrite an answer committed by the first tab', async ({ user, data, vocabulary }) => {
  await selectQuestions(user)
  const deck = await data.create({ name: 'Two tab recovery', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await startStudy(user.page, deck.id)
  const other = await user.page.context().newPage()
  try {
    await other.goto(user.page.url())
    await expect(other.getByRole('button', { name: "I don’t know", exact: true })).toBeVisible()
    await answerChoice(user.page, 'bank')
    await other.getByRole('button').filter({ hasText: 'bank' }).click()
    await expect(other.getByText('This session changed in another tab. Reload to continue from the latest answer.', { exact: true })).toBeVisible()
    expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 0 })
    await other.reload()
    await expect(other.getByText('That fits.', { exact: true })).toBeVisible()
    await finishStudy(other)
    expect(await user.api.call('study/activity')).toMatchObject({ applied_events: 1 })
  } finally { await other.close() }
})

test('storage failure prevents silently advancing or writing progress', async ({ user, data, vocabulary }) => {
  await selectQuestions(user)
  const deck = await data.create({ name: 'Storage recovery', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await startStudy(user.page, deck.id)
  await user.page.evaluate(() => {
    const original = Storage.prototype.setItem
    Storage.prototype.setItem = function (key, value) {
      if (key.includes('study')) throw new DOMException('Storage unavailable', 'QuotaExceededError')
      original.call(this, key, value)
    }
  })
  await user.page.getByRole('button').filter({ hasText: 'bank' }).click()
  await expect(user.page.getByText('This browser cannot save the session. Free storage space and retry.', { exact: true })).toBeVisible()
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 0 })
  await user.page.reload()
  await answerChoice(user.page, 'bank')
  await finishStudy(user.page)
})

test('failed preparation is visible and an explicit retry prepares through the real API', async ({ user, data, vocabulary }) => {
  await selectQuestions(user)
  const deck = await data.create({ name: 'Preparation retry', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  let failed = false
  await user.page.route('**/v1/study:prepare', async route => {
    if (!failed) { failed = true; await route.abort('connectionreset') }
    else await route.continue()
  })
  await user.page.goto(`/app/learn?node=${deck.id}&selection=new`)
  await expect(user.page.getByRole('alertdialog')).toBeVisible()
  await user.page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(user.page.getByRole('button', { name: "I don’t know", exact: true })).toBeVisible()
  await answerChoice(user.page, 'bank')
  await finishStudy(user.page)
})

test('a failed typed grade keeps the entered answer available for a real retry', async ({ user, data, vocabulary }) => {
  await data.prepareUser({ plan: 'pro' })
  await selectQuestions(user, 'definition_to_word', 'single_word')
  const deck = await data.create({ name: 'Grading retry', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await startStudy(user.page, deck.id)
  const input = user.page.getByRole('textbox', { name: 'Your word', exact: true })
  await input.fill('bank')
  let failed = false
  await user.page.route('**/v1/study:grade', async route => {
    if (!failed) { failed = true; await route.abort('connectionreset') }
    else await route.continue()
  })
  await user.page.getByRole('button', { name: /^Check answer/ }).click()
  await expect(input).toHaveValue('bank')
  await expect(user.page.getByRole('alert').filter({ hasText: 'Failed to fetch' })).toBeVisible()
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 0 })
  await user.page.getByRole('button', { name: 'Retry grading', exact: true }).click()
  await expect(user.page.getByText('That fits.', { exact: true })).toBeVisible()
  await finishStudy(user.page)
})

test('a cold question bank reports model rejection and retry builds validated questions without writing progress', async ({ user, data, vocabulary, scenarios }) => {
  await selectQuestions(user)
  const deck = await data.create({ name: 'Cold historical archive', type: 'deck', sense_ids: [vocabulary.archiveCollection.sense_id] })
  await scenarios.register({ id: randomUUID(), path: '/chat/completions', contains: 'a collection of historical records', responses: [
    { status: 400, body: { error: { type: 'invalid_request_error', message: 'Controlled artifact rejection' } } },
    { status: 200, body: structuredCompletion({ artifacts: [{
      corrects: ['a collection of historical records'],
      distractors: [{ word: 'orchard', definition: 'land where fruit trees grow' }, { word: 'bakery', definition: 'a shop that makes and sells bread' }, { word: 'station', definition: 'a place where trains stop' }],
    }] }) },
  ] })
  await user.page.goto(`/app/learn?node=${deck.id}&selection=new`)
  await expect(user.page.getByRole('alertdialog')).toBeVisible()
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 0 })
  await user.page.getByRole('button', { name: 'Retry', exact: true }).click()
  await answerChoice(user.page, 'archive')
  await finishStudy(user.page)
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 1 })
})

test('unusable saved study data is replaced by preparation without progress writes', async ({ user, data, vocabulary }) => {
  await selectQuestions(user)
  const deck = await data.create({ name: 'Recover saved learning', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await user.page.evaluate(({ user, node }) => localStorage.setItem(`pycil:study:${user}:${node}`, '{invalid'), { user: user.account.id, node: deck.id })
  await startStudy(user.page, deck.id)
  await expect(user.page.getByRole('alertdialog')).not.toBeVisible()
  await answerChoice(user.page, 'bank')
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 0 })
  await finishStudy(user.page)
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 1 })
})

test('exiting while real preparation is delayed leaves no session or submitted review', async ({ user, data, vocabulary }) => {
  await selectQuestions(user)
  const deck = await data.create({ name: 'Cancelled preparation', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  let release!: () => void
  let reached!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  const received = new Promise<void>(resolve => { reached = resolve })
  const submitted: string[] = []
  user.page.on('request', request => { if (request.url().endsWith('/study:submitResults')) submitted.push(request.method()) })
  await user.page.route('**/v1/study:prepare', async route => {
    const response = await route.fetch()
    expect(response.status()).toBe(202)
    reached()
    await held
    await route.fulfill({ response }).catch(() => {})
  })
  try {
    await user.page.goto(`/app/learn?node=${deck.id}&selection=new`)
    await received
    await user.page.getByRole('button', { name: 'Exit learning mode', exact: true }).click()
    await expect(user.page).toHaveURL(new RegExp(`/app/personal/${deck.id}$`))
    release()
    expect(await user.page.evaluate(({ user, node }) => localStorage.getItem(`pycil:study:${user}:${node}`), { user: user.account.id, node: deck.id })).toBeNull()
    expect(submitted).toEqual([])
    expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 0 })
  } finally { release() }
})

test('empty and unavailable study scopes expose recovery within learning mode', async ({ user, data }) => {
  const deck = await data.create({ name: 'Empty learning scope', type: 'deck' })
  await user.page.goto(`/app/learn?node=${deck.id}&selection=new`)
  await expect(user.page.getByRole('alertdialog')).toContainText('No eligible questions')
  await user.page.getByRole('button', { name: 'Back to My Library', exact: true }).click()
  await expect(user.page).toHaveURL(new RegExp(`/app/personal/${deck.id}$`))
  await user.page.goto('/app/learn?node=00000000-0000-0000-0000-000000000000&selection=new')
  await expect(user.page.getByRole('alertdialog')).toContainText('This material could not be found.')
})
