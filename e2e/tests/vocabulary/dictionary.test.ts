import { randomUUID } from 'node:crypto'
import { structuredCompletion } from '../../support/model-provider.ts'
import { test, expect } from '../../fixtures/index.ts'

test('a ready word exposes distinct meanings and adds the selected meaning to an existing deck', async ({ user, data, vocabulary }) => {
  const deck = await data.create({ name: 'Dictionary additions', type: 'deck' })
  await user.page.goto(`/dictionary?q=bank&word=${vocabulary.bankFinancial.word_id}`)
  await expect(user.page.getByRole('heading', { name: 'bank', exact: true })).toBeVisible()
  await expect(user.page.locator('article')).toContainText('an institution where people keep and borrow money')
  await expect(user.page.locator('article')).toContainText('the ground along the side of a river')
  const sense = user.page.locator('article section').filter({ hasText: 'an institution where people keep and borrow money' })
  await sense.getByRole('button', { name: 'Add to deck', exact: true }).click()
  const dialog = user.page.getByRole('dialog', { name: 'Choose a destination', exact: true })
  await dialog.getByRole('button', { name: 'Personal', exact: true }).click()
  await dialog.getByRole('button', { name: `${deck.name} Deck`, exact: true }).click()
  await dialog.getByRole('button', { name: 'Add to deck', exact: true }).click()
  await expect(user.page.getByText('Meaning added to deck', { exact: true })).toBeVisible()
  const contents = await user.api.call<{ senses: { sense_id: number }[] }>(`nodes/${deck.id}/senses`)
  expect(contents.senses.map(item => item.sense_id)).toEqual([vocabulary.bankFinancial.sense_id])
})

test('a reference entry is explicitly unprepared, can be prepared by Taskiq worker, reveals article and senses, and adds sense to deck', async ({ user, data, scenarios }) => {
  const deck = await data.create({ name: 'Worker additions', type: 'deck' })
  await scenarios.register({
    id: randomUUID(),
    path: '/chat/completions',
    contains: 'jetty',
    responses: [
      {
        status: 200,
        body: structuredCompletion({
          lemma: 'jetty',
          type: 'word',
          aliases: [],
          related: [],
          senses: [
            {
              definition: 'a wooden or stone structure built out into the water as a landing place for boats',
              pos: 'noun',
              references: ['a1'],
            },
          ],
        }),
      },
      {
        status: 200,
        body: structuredCompletion({
          senses: [
            {
              sense_id: 1,
              tier: 'common',
              cefr_level: 'b1',
              register: null,
              examples: ['They walked along the [jetty] to look at the boats.'],
              forms: ['jetty', 'jetties'],
              patterns: [],
              collocations: [],
              relations: [],
            },
          ],
        }),
      },
    ],
  })

  await user.page.goto('/dictionary?q=jetty')
  await user.page.getByRole('button').filter({ hasText: 'jetty' }).click()
  const prepare = user.page.getByRole('button', { name: 'Prepare entry', exact: true })
  await expect(prepare).toBeVisible()
  await expect(user.page.locator('article').getByRole('heading', { name: 'jetty', exact: true })).not.toBeVisible()
  expect(await user.api.call('study/progress')).toMatchObject({ total: 0 })

  await prepare.click()
  const article = user.page.locator('article')
  await expect(article.getByRole('heading', { name: 'jetty', exact: true })).toBeVisible({ timeout: 30_000 })
  await expect(article).toContainText('a wooden or stone structure built out into the water as a landing place for boats')
  await expect(prepare).not.toBeVisible()

  const sense = user.page.locator('article section').filter({ hasText: 'a wooden or stone structure built out into the water as a landing place for boats' })
  await sense.getByRole('button', { name: 'Add to deck', exact: true }).click()
  const dialog = user.page.getByRole('dialog', { name: 'Choose a destination', exact: true })
  await dialog.getByRole('button', { name: 'Personal', exact: true }).click()
  await dialog.getByRole('button', { name: `${deck.name} Deck`, exact: true }).click()
  await dialog.getByRole('button', { name: 'Add to deck', exact: true }).click()
  await expect(user.page.getByText('Meaning added to deck', { exact: true })).toBeVisible()
  const contents = await user.api.call<{ senses: { sense_id: number }[] }>(`nodes/${deck.id}/senses`)
  expect(contents.senses).toHaveLength(1)
  expect(contents.senses[0].sense_id).toBeGreaterThan(0)
  expect(await user.api.call('study/progress')).toMatchObject({ total: 1 })
})

test('the word picker retains selections across searches and preserves a concurrent addition', async ({ user, data, vocabulary }) => {
  const deck = await data.create({ name: 'Selected meanings', type: 'deck' })
  await user.page.goto(`/app/personal/${deck.id}/words`)
  await user.page.getByRole('button', { name: 'Add words', exact: true }).click()
  const picker = user.page.getByRole('dialog', { name: 'Add words to deck', exact: true })
  const search = picker.getByRole('searchbox', { name: 'Search words', exact: true })
  await search.fill('bank')
  await picker.getByRole('checkbox', { name: /an institution where people keep and borrow money/ }).check()
  await search.fill('archive')
  await picker.getByRole('checkbox', { name: /a collection of historical records/ }).check()
  await expect(picker.getByText('2 meanings selected', { exact: true })).toBeVisible()
  await user.api.call(`nodes/${deck.id}:modifySenses`, 'POST', { add: [vocabulary.bankRiver.sense_id], remove: [] })
  await picker.getByRole('button', { name: 'Add to deck', exact: true }).click()
  await expect(picker).not.toBeVisible()
  const senses = await user.api.call<{ senses: { sense_id: number }[] }>(`nodes/${deck.id}/senses`)
  expect(senses.senses.map(sense => sense.sense_id).sort((a, b) => a - b)).toEqual([vocabulary.bankFinancial.sense_id, vocabulary.bankRiver.sense_id, vocabulary.archiveCollection.sense_id].sort((a, b) => a - b))
})

test('adding a Dictionary meaning can create a deck in a nested folder', async ({ user, data, vocabulary }) => {
  const folder = await data.create({ name: 'Dictionary destination', type: 'folder' })
  await user.page.goto(`/dictionary?q=bank&word=${vocabulary.bankFinancial.word_id}`)
  await user.page.locator('article section').filter({ hasText: 'an institution where people keep and borrow money' }).getByRole('button', { name: 'Add to deck', exact: true }).click()
  const destination = user.page.getByRole('dialog', { name: 'Choose a destination', exact: true })
  await destination.getByRole('button', { name: 'Personal', exact: true }).click()
  await destination.getByRole('button', { name: folder.name, exact: true }).click()
  await destination.getByRole('button', { name: `Create a deck in ${folder.name}`, exact: true }).click()
  await destination.getByRole('textbox', { name: 'New deck name', exact: true }).fill('Created from Dictionary')
  const created = user.page.waitForResponse(response => response.url().endsWith('/v1/nodes') && response.request().method() === 'POST')
  await destination.getByRole('button', { name: 'Create and add', exact: true }).click()
  const response = await created
  expect(response.status()).toBe(201)
  const deck = await response.json()
  data.track(deck.id)
  expect(deck).toMatchObject({ name: 'Created from Dictionary', parent_id: folder.id, sense_ids: [vocabulary.bankFinancial.sense_id] })
  await user.page.goto(`/app/personal/${deck.id}/words`)
  await expect(user.page.getByRole('button', { name: /View bank: an institution/ })).toBeVisible()
})

test('native aliases and inflections find ready words and reveal the matching lexical detail', async ({ user }) => {
  await user.page.goto('/dictionary?q=colour')
  await user.page.getByRole('button', { name: /color.*Ready/ }).click()
  await expect(user.page.locator('article')).toContainText('colour')
  await user.page.getByRole('searchbox', { name: 'Search word or expression', exact: true }).fill('banking')
  await user.page.getByRole('button', { name: /bank.*Matched.*banking/ }).click()
  await user.page.getByRole('tab', { name: /^verb/ }).click()
  await expect(user.page.locator('article')).toContainText('to put money into a bank account')
  await expect(user.page.locator('article')).toContainText('banking')
  await expect(user.page.locator('article')).toContainText('banked')
})
