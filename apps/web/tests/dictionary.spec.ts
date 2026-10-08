import { expect, test } from '@playwright/test'
import { createMockServices } from '../src/lib/services/mock'
import { createHttpServices } from '../src/lib/services/http'
import database from '../src/lib/services/mock/database.json' with { type: 'json' }
import { parseDictionaryWord } from '../src/lib/dictionary-model'

const signal = () => new AbortController().signal

test('Dictionary adds one meaning to an existing deck and creates a deck with a meaning', async ({ page }) => {
  await page.goto('/app/dictionary')
  await page.getByRole('searchbox', { name: 'Search word or expression' }).fill('run')
  await page.getByRole('button', { name: /run.*Ready/i }).click()
  await expect(page.getByRole('heading', { name: 'run', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Add to deck' }).first().click()
  const destination = page.getByRole('dialog', { name: 'Choose a destination' })
  await destination.getByRole('button', { name: 'Personal' }).dblclick()
  await destination.getByRole('button', { name: /Everyday conversation.*Deck/ }).click()
  await destination.getByRole('button', { name: 'Add to deck' }).click()
  await expect(page.getByText(/In 1 deck/).first()).toBeVisible()

  await page.getByRole('button', { name: 'Add to deck' }).nth(1).click()
  await destination.getByRole('button', { name: 'Personal' }).dblclick()
  await destination.getByRole('button', { name: /Create a deck in Personal/ }).click()
  await destination.getByRole('textbox', { name: 'New deck name' }).fill('New verbs')
  await destination.getByRole('button', { name: 'Create and add' }).click()
  await expect(page.getByRole('link', { name: 'New verbs', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'New verbs 1 sense' })).toBeVisible()
})

test('Word picker keeps sense selection across searches and saves a batch', async ({ page }) => {
  await page.goto('/app/personal/everyday/words')
  await page.getByRole('button', { name: 'Add words' }).click()
  const picker = page.getByRole('dialog', { name: 'Add words to deck' })
  await picker.getByRole('searchbox', { name: 'Search words' }).fill('run')
  await expect(picker.getByRole('heading', { name: 'run' })).toBeVisible()
  await picker.getByRole('checkbox').first().check()
  await picker.getByRole('searchbox', { name: 'Search words' }).fill('bank')
  await expect(picker.getByText('1 meaning selected')).toBeVisible()
  await picker.getByRole('checkbox').first().check()
  await picker.getByRole('button', { name: 'Add to deck' }).click()
  await expect(picker).toHaveCount(0)
  await page.getByRole('searchbox', { name: 'Search words' }).fill('run')
  await expect(page.getByRole('table').getByRole('row', { name: /run/ })).toBeVisible()
  await page.getByRole('button', { name: /View run: to move quickly on foot/ }).click()
  await page.getByRole('button', { name: 'Remove from deck' }).click()
  await expect(page.getByText('No matching words.', { exact: true })).toBeVisible()
})

test('Available entry prepares into a readable word', async ({ page }) => {
  await page.goto('/app/dictionary')
  await page.getByRole('searchbox', { name: 'Search word or expression' }).fill('orbit')
  await page.getByRole('button', { name: /orbit.*Needs preparation/i }).click()
  await expect(page.getByRole('heading', { name: 'orbit', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Prepare entry' }).click()
  await expect(page).toHaveURL(/\/app\/dictionary$/)
  await expect(page.getByText('the curved path of an object around a planet or star')).toBeVisible()
})

test('Destination search opens a nested folder with its full breadcrumb', async ({ page }) => {
  await page.goto('/app/dictionary')
  await page.getByRole('searchbox', { name: 'Search word or expression' }).fill('run')
  await page.getByRole('button', { name: /run.*Ready/i }).click()
  await page.getByRole('button', { name: 'Add to deck' }).first().click()
  const destination = page.getByRole('dialog', { name: 'Choose a destination' })
  await destination.getByRole('textbox', { name: 'Search folders and decks' }).fill('Presentations')
  await destination.getByRole('button', { name: /Presentations/ }).dblclick()
  await expect(destination.getByRole('navigation', { name: 'Destination path' })).toContainText('Business English')
  await expect(destination.getByRole('navigation', { name: 'Destination path' })).toContainText('Presentations')
})

test('membership deltas and preparation are consistent in the mock contract', async () => {
  const services = createMockServices({ latency: 0 })
  const run = await services.dictionary.search('run', signal())
  expect(run.words[0].word_id).toBe(1001)
  const [preview] = await services.dictionary.previews([1001], signal())
  expect(preview.senses).toHaveLength(10)
  expect(preview.senses.slice(0, 3).map(sense => sense.id)).toEqual([49, 50, 51])
  await services.library.updateDeckSenses('everyday', { add: [49, 50], remove: [] }, signal())
  await services.library.updateDeckSenses('everyday', { add: [49], remove: [50] }, signal())
  expect((await services.library.meanings('everyday', { q: 'run' }, signal())).senses.map(sense => sense.sense_id)).toEqual([49])
  const created = await services.library.createDeck('preview-personal', 'Verbs', [51], signal())
  expect((await services.dictionary.context(1001, signal())).senses.find(sense => sense.sense_id === 51)?.decks).toContainEqual({ id: created, name: 'Verbs', owner_id: 'preview-alex', space: 'PERSONAL' })
  const orbit = (await services.dictionary.search('orbit', signal())).available[0]
  const job = await services.dictionary.prepare(orbit.available_id, orbit.display, signal())
  await services.dictionary.generation(job.generation_id, signal())
  expect((await services.dictionary.generation(job.generation_id, signal())).status).toBe('SUCCEEDED')
  expect((await services.dictionary.search('orbit', signal())).words[0].word_id).toBe(1002)
})

test('Dictionary selection stays on one page and reveals native sense detail', async ({ page }) => {
  await page.goto('/app/dictionary')
  const search = page.getByRole('searchbox', { name: 'Search word or expression' })
  await expect(search).toHaveAttribute('type', 'text')
  await search.fill('bank')
  await expect(page.getByRole('button', { name: 'Clear search' })).toHaveCount(1)
  await page.evaluate(() => { Object.defineProperty(window, 'dictionaryNavigationProbe', { value: true }) })
  await page.getByRole('button', { name: /bank.*Ready/i }).click()
  await expect(page).toHaveURL(/\/app\/dictionary$/)
  expect(await page.evaluate(() => 'dictionaryNavigationProbe' in window)).toBe(true)
  await expect(page.getByText('5 senses')).toBeVisible()
  await expect(page.getByText('CEFR A2').first()).toBeVisible()
  await expect(page.getByText('open a bank account')).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search word or expression' }).fill('light')
  await page.getByRole('button', { name: /light.*Ready/i }).click()
  await expect(page.getByText('5 senses')).toBeVisible()
  expect(await page.evaluate(() => 'dictionaryNavigationProbe' in window)).toBe(true)
})

test('invented lexical fixture follows Word and Sense DTOs', () => {
  const words = database.dictionary.words.map(parseDictionaryWord)
  const pending = database.dictionary.pending_words.map(parseDictionaryWord)
  expect(words).toHaveLength(52)
  expect(words.find(word => word.lemma === 'run')?.senses).toHaveLength(10)
  expect(words.find(word => word.lemma === 'bank')?.senses).toHaveLength(5)
  expect(words.find(word => word.lemma === 'light')?.senses.map(sense => sense.pos)).toContain('ADJECTIVE')
  expect(pending.find(word => word.lemma === 'orbit')?.senses).toHaveLength(3)
  const senses = [...words, ...pending].flatMap(word => word.senses)
  expect(new Set(senses.map(sense => sense.id)).size).toBe(senses.length)
  expect(senses.every(sense => sense.definition && sense.examples.length > 0 && sense.tier)).toBe(true)
})

test('live adapter sends a membership delta without reading or replacing a deck', async () => {
  const original = globalThis.fetch
  const requests: { path: string; method: string; body: unknown }[] = []
  globalThis.fetch = async (url, init) => {
    requests.push({ path: String(url), method: init?.method ?? 'GET', body: JSON.parse(String(init?.body)) })
    return new Response(JSON.stringify({ total: 1 }))
  }
  try {
    await createHttpServices(async () => 'test-token').library.updateDeckSenses('deck', { add: [49], remove: [50] }, signal())
    expect(requests).toEqual([{ path: '/api/v1/nodes/deck:modifySenses', method: 'POST', body: { add: [49], remove: [50] } }])
  } finally { globalThis.fetch = original }
})
