import database from '../../../src/lib/api/services/mock/database.json' with { type: 'json' }

import { expect,test } from 'vitest'

import { createMockServices } from '../../../src/lib/api/services/mock'

import { reportingDay,shiftDay } from '../../../src/features/home/calendar'

import { createHttpServices } from '../../../src/lib/api/services/http'

import { libraryNodeKind } from '../../../src/features/library/model'

import { MatchKind,parseDictionaryWord } from '../../../src/lib/api/vocabulary'

const now = () => new Date('2026-10-07T02:00:00Z')

const signal = () => new AbortController().signal

test('profile edits persist all public fields and reject duplicate handles atomically', async () => {
  const services = createMockServices({ latency: 0 })
  const updated = await services.account.updateProfile({ display_name: ' Nguyễn Ninh ', handle: ' NINH ', bio: ' Hello ' }, signal())
  expect(updated).toMatchObject({ display_name: 'Nguyễn Ninh', handle: 'ninh', bio: 'Hello' })
  await expect(services.account.updateProfile({ display_name: 'Should not persist', handle: 'sam' }, signal())).rejects.toMatchObject({ status: 409, code: 'handle_unavailable' })
  expect(await services.account.profile(signal())).toMatchObject({ display_name: 'Nguyễn Ninh', handle: 'ninh', bio: 'Hello' })
  for (const name of [' ', 'a'.repeat(256)]) await expect(services.account.updateProfile({ display_name: name }, signal())).rejects.toMatchObject({ status: 422 })
  expect(await services.account.updateProfile({ bio: null }, signal())).toMatchObject({ display_name: 'Nguyễn Ninh', handle: 'ninh', bio: null })
})

test('assistant settings are independent of learning settings and start disabled', async () => {
  const services = createMockServices({ latency: 0 })
  const before = await services.account.profile(signal())
  expect(before.settings.assistant.auto_approve).toBe(false)
  const changed = await services.account.updateSettings({ assistant: { auto_approve: true } }, signal())
  expect(changed.settings.assistant.auto_approve).toBe(true)
  expect(changed.settings.learning).toEqual(before.settings.learning)
  const refreshed = await services.account.updateSettings({ locale: 'vi' }, signal())
  expect(refreshed.settings.assistant.auto_approve).toBe(true)
})

test('Free quiz selection preserves saved Pro formats and prepares the effective pair', async () => {
  const seed = structuredClone(database)
  seed.account.plan = 'free'
  seed.account.learning_options.advanced_grading = false
  seed.account.settings.learning.question_types = ['definition_to_word']
  seed.account.settings.learning.formats = ['single_word']
  const services = createMockServices({ database: seed, latency: 0 })
  const profile = await services.account.updateSettings({ learning: { question_types: ['meaning_in_context'] } }, signal())
  expect(profile.settings.learning.formats).toEqual(['single_word'])
  expect(profile.effective_learning?.formats).toEqual(['single_choice'])
  const prepared = await services.learning.prepare({ node_id: 'everyday', selection: 'new', max_sense_count: 1 }, signal())
  expect(prepared.bundles).toHaveLength(1)
  expect(prepared.bundles[0].questions.every(item => item.question.question_type === 'meaning_in_context' && item.format === 'single_choice')).toBe(true)
  seed.account.plan = 'pro'
  seed.account.learning_options.advanced_grading = true
  const pro = createMockServices({ database: seed, latency: 0 })
  await expect(pro.account.updateSettings({ learning: { question_types: ['meaning_in_context'] } }, signal())).rejects.toMatchObject({ status: 422 })
})

test('JSON adapter implements the shared contract entirely offline and protects the seed', async () => {
  const original = globalThis.fetch
  let calls = 0
  globalThis.fetch = async () => { calls++; throw new Error('Mock mode must never fetch') }
  try {
    const service = createMockServices({ now, latency: 0 })
    const profile = await service.account.profile(signal())
    const summary = await service.learning.summary(undefined, signal())
    expect(profile.display_name).toBe(database.account.display_name)
    expect(summary).toMatchObject(database.summary)
    const today = reportingDay(now(), profile.settings!.timezone)
    const activity = await service.learning.activity({ start: shiftDay(today, -6), end: today }, signal())
    expect(activity.days).toHaveLength(7)
    expect(activity.current_streak).toBe(6)
    expect(activity.applied_events + activity.practice_events).toBe(activity.days.reduce((sum, day) => sum + day.applied_events + day.practice_events, 0))
    const schedule = await service.learning.schedule({ start: today, end: shiftDay(today, 6) }, signal())
    expect(schedule.days.map(day => day.count)).toEqual(database.schedule.map(day => day.count))
    const library = await service.library.list(profile.personal_node_id, signal())
    expect(library.nodes).toHaveLength(4)
    expect(library.nodes.find(node => node.id === 'saved-business')).toMatchObject({ type: 'reference', target_type: 'folder' })
    expect((await service.learning.prepare({ node_id: profile.library_node_id, selection: 'due' }, signal())).actual_sense_count).toBe(10)
    profile.display_name = 'Mutated'
    library.nodes[0].name = 'Mutated'
    expect((await service.account.profile(signal())).display_name).toBe('Alex')
    expect((await service.library.list(profile.personal_node_id, signal())).nodes[0].name).toBe('Everyday conversation')
    expect(calls).toBe(0)
  } finally { globalThis.fetch = original }
})

test('mock cancellation, invalid scopes and selection modes behave like a service, not component constants', async () => {
  const service = createMockServices({ now, latency: 100 })
  const controller = new AbortController()
  const pending = service.learning.summary(undefined, controller.signal)
  controller.abort(new Error('Cancelled'))
  await expect(pending).rejects.toThrow('Cancelled')
  await expect(service.learning.summary('not-a-node', signal())).rejects.toMatchObject({ status: 404 })
  const db = structuredClone(database)
  db.summary.due = 0; db.summary.not_due = db.summary.studied; db.library.due_sense_ids = []
  const noDue = createMockServices({ database: db, now, latency: 0 })
  expect((await noDue.learning.prepare({ node_id: db.account.library_node_id, selection: 'due' }, signal())).actual_sense_count).toBe(0)
  expect((await noDue.learning.prepare({ node_id: db.account.library_node_id, selection: 'new', max_sense_count: 3 }, signal())).actual_sense_count).toBe(3)
})

test('preview Discovery, references and publication use the shared Library state', async () => {
  const service = createMockServices({ latency: 0 })
  const profile = await service.account.profile(signal())
  const id = await service.library.createDeck(profile.personal_node_id, 'Publish this', [1], signal())
  await expect(service.library.moveNode(id, profile.published_node_id, signal())).rejects.toMatchObject({ status: 409 })
  await service.library.moveNode(id, profile.published_node_id, signal(), { confirm: true, retainReference: true })
  expect((await service.library.discovery({ q: 'Publish this' }, signal())).nodes.map(node => node.id)).toContain(id)
  const reference = await service.library.createReference(profile.personal_node_id, id, 'Saved', signal())
  expect((await service.library.metadata(reference, signal())).target?.id).toBe(id)
  expect((await service.library.meanings(reference, {}, signal())).senses.map(sense => sense.sense_id)).toEqual([1])
  expect((await service.library.sources(reference, 1, undefined, signal())).decks.map(deck => deck.id)).toEqual([id])
  await expect(service.library.sources(reference, 2, undefined, signal())).rejects.toMatchObject({ status: 404 })
})

test('references use the existing create endpoint and enforce publication boundaries', async () => {
  const service = createMockServices({ latency: 0, now })
  const published = database.account.published_node_id
  await expect(service.library.createReference(published, 'travel-source', 'Travel', signal())).rejects.toMatchObject({ code: 'publication_confirmation_required' })
  await expect(service.library.createReference(published, 'everyday', 'Private', signal(), true)).rejects.toMatchObject({ code: 'private_reference_cannot_be_published' })
  const id = await service.library.createReference(published, 'travel-source', 'Travel', signal(), true)
  expect((await service.library.metadata(id, signal())).target?.id).toBe('travel-source')
  const original = globalThis.fetch
  const requests: unknown[] = []
  globalThis.fetch = async (_, options) => {
    requests.push(JSON.parse(options!.body as string))
    return Response.json({ id })
  }
  try {
    await createHttpServices(async () => 'test-only-bearer').library.createReference(published, 'travel-source', 'Travel', signal(), true)
    expect(requests).toEqual([{ type: 'reference', name: 'Travel', parent_id: published, reference_id: 'travel-source', confirm_publication: true }])
  } finally { globalThis.fetch = original }
})

test('Library mock is canonical, scoped, deduplicated and consistent with Home', async () => {
  const service = createMockServices({ latency: 0, now })
  const root = await service.library.metadata(database.account.library_node_id, signal())
  const rootSummary = await service.learning.summary(root.id, signal())
  expect(rootSummary).toMatchObject(database.summary)
  const home = await service.learning.summary(undefined, signal())
  expect(home).toMatchObject({ total: rootSummary.total, due: rootSummary.due, new: rootSummary.new, not_due: rootSummary.not_due })
  const folder = await service.library.metadata('business', signal())
  const folderSummary = await service.learning.summary(folder.id, signal())
  const children = await service.library.contents('business', {}, signal())
  expect(children.nodes.map(node => node.name)).toEqual(['Meetings', 'Emails', 'Presentations', 'Business Core', 'Workplace Verbs'])
  const meanings = await service.library.meanings('business', { limit: 100 }, signal())
  expect(meanings.senses).toHaveLength(folderSummary.total)
  expect(new Set(meanings.senses.map(sense => sense.sense_id)).size).toBe(folderSummary.total)
  expect(meanings.senses.filter(sense => sense.learning!.state === 'due')).toHaveLength(folderSummary.due)
  expect(meanings.senses.filter(sense => sense.learning!.state === 'new')).toHaveLength(folderSummary.new)
  const agenda = meanings.senses.find(sense => sense.lemma === 'agenda')!
  expect(agenda.sources.map(source => source.id).sort()).toEqual(['business-core', 'meeting-expressions'])
  expect(folder.breadcrumbs.map(node => node.name)).toEqual(['My Library', 'Personal', 'Business English'])
})

test('meaning pagination, search, filters and sort do not leak other scopes', async () => {
  const service = createMockServices({ latency: 0, now })
  const first = await service.library.meanings('everyday', {}, signal())
  const second = await service.library.meanings('everyday', { cursor: first.next_cursor! }, signal())
  expect(first.senses).toHaveLength(12)
  expect(first.next_cursor).not.toBeNull()
  expect(new Set([...first.senses, ...second.senses].map(sense => sense.sense_id)).size).toBe(24)
  await expect(service.library.meanings('business-core', { cursor: first.next_cursor! }, signal())).rejects.toMatchObject({ code: 'invalid_cursor' })
  const banks = await service.library.meanings('everyday', { q: 'bank' }, signal())
  expect(banks.senses.map(sense => sense.definition)).toEqual(['an organization where people keep or borrow money', 'the land along the side of a river'])
  expect((await service.library.meanings('business-core', { q: 'bank' }, signal())).senses).toEqual([])
  const due = await service.library.meanings('everyday', { state: 'due' }, signal())
  expect(due.senses.every(sense => sense.learning!.state === 'due')).toBe(true)
  const reviewed = await service.library.meanings('everyday', { sort: 'last_reviewed_desc', limit: 100 }, signal())
  const dates = reviewed.senses.map(sense => sense.learning!.last_reviewed_at ?? '')
  expect(dates).toEqual([...dates].sort().reverse())
  const search = await service.library.contents('business', { q: 'Email' }, signal())
  expect(search.nodes.some(node => node.id === 'email-expressions')).toBe(true)
  expect(search.nodes.some(node => node.id === 'travel-source')).toBe(false)
})

test('references preserve placement but resolve readable sources; missing targets expose no contents', async () => {
  const service = createMockServices({ latency: 0, now })
  const reference = await service.library.metadata('travel', signal())
  const source = await service.library.metadata('travel-source', signal())
  expect(reference.owner_id).toBe(database.account.id)
  expect(source.owner_id).not.toBe(database.account.id)
  expect(reference.target?.id).toBe(source.id)
  expect((await service.learning.summary(reference.id, signal())).total).toBe((await service.learning.summary(source.id, signal())).total)
  expect(source.breadcrumbs).toEqual([{ id: 'preview-sam-published', name: 'Published' }, { id: 'travel-source', name: 'Travel essentials' }])
  expect((await service.library.meanings('travel', {}, signal())).senses.map(sense => sense.sense_id)).toEqual((await service.library.meanings('travel-source', {}, signal())).senses.map(sense => sense.sense_id))
  expect((await service.library.contents(database.account.personal_node_id, {}, signal())).nodes.find(node => node.id === 'travel')?.target_type).toBe('deck')
  const savedBusiness = await service.library.metadata('saved-business', signal())
  expect(savedBusiness.target).toMatchObject({ id: 'business', type: 'folder' })
  expect(await service.learning.summary(savedBusiness.id, signal())).toMatchObject(database.nodes.find(node => node.id === 'saved-business')!.counts)
  expect((await service.library.contents('saved-business', {}, signal())).nodes.map(node => node.id)).toEqual((await service.library.contents('business', {}, signal())).nodes.map(node => node.id))
  expect((await service.library.meanings('saved-business', { limit: 100 }, signal())).senses.map(sense => sense.sense_id)).toEqual((await service.library.meanings('business', { limit: 100 }, signal())).senses.map(sense => sense.sense_id))
  const emails = await service.library.contents('emails', {}, signal())
  const folderReference = emails.nodes.find(node => node.id === 'saved-meetings')!
  expect(libraryNodeKind(folderReference)).toBe('folder')
  expect((await service.library.metadata(folderReference.id, signal())).target?.type).toBe('folder')
  expect((await service.library.contents(folderReference.id, {}, signal())).nodes.map(node => node.id)).toEqual(['meeting-expressions'])
  const unavailable = await service.library.metadata('unavailable-reference', signal())
  expect(unavailable.target).toBeNull()
  expect(unavailable.reference_available).toBe(false)
  await expect(service.learning.summary(unavailable.id, signal())).rejects.toMatchObject({ code: 'reference_unavailable' })
  await expect(service.library.meanings(unavailable.id, {}, signal())).rejects.toMatchObject({ code: 'reference_unavailable' })
  await expect(service.library.metadata('not-a-node', signal())).rejects.toMatchObject({ status: 404 })
})

test('empty decks, cancellation and returned-object isolation preserve seed content', async () => {
  const service = createMockServices({ latency: 0, now })
  const empty = await service.library.metadata('empty-deck', signal())
  expect((await service.learning.summary(empty.id, signal())).total).toBe(0)
  expect((await service.library.meanings('empty-deck', {}, signal())).senses).toEqual([])
  const result = await service.library.metadata('everyday', signal())
  result.name = 'Changed'
  expect((await service.library.metadata('everyday', signal())).name).toBe('Everyday conversation')
  const controller = new AbortController()
  controller.abort()
  await expect(service.library.meanings('everyday', {}, controller.signal)).rejects.toBeDefined()
})

test('mock search keeps surface origin priority for every supported match class', async () => {
  const fixture = structuredClone(database)
  const template = fixture.dictionary.words[0]
  fixture.dictionary.words = [
    { ...structuredClone(template), id: 1, lemma: 'running', aliases: [], senses: [] },
    { ...structuredClone(template), id: 2, lemma: 'z-alias', aliases: ['running'], senses: [] },
    { ...structuredClone(template), id: 3, lemma: 'a-form', aliases: [], senses: [
      { ...structuredClone(template.senses[0]), word_id: 3, forms: [{ surface: 'running', inf: 'ing' }] },
    ] },
    { ...structuredClone(template), id: 4, lemma: 'b-alias', aliases: ['running'], senses: [] },
  ] as typeof fixture.dictionary.words
  fixture.dictionary.references = []
  const services = createMockServices({ database: fixture, latency: 0 })
  for (const [query, kind] of [['running', MatchKind.EXACT], ['runn', MatchKind.PREFIX], ['unning', MatchKind.SUBSTRING]]) {
    const hits = (await services.dictionary.search(query, signal())).items
    expect(hits.map(hit => hit.kind === 'word' ? hit.word_id : null)).toEqual([1, 4, 2, 3])
    expect(hits.every(hit => hit.match_kind === kind && hit.matched_surface === 'running')).toBe(true)
  }
})

test('membership deltas and preparation are consistent in the mock contract', async () => {
  const services = createMockServices({ latency: 0 })
  const run = await services.dictionary.search('run', signal())
  expect(run.items[0]).toMatchObject({ kind: 'word', word_id: 1001, match_kind: 'exact' })
  const [preview] = await services.dictionary.previews([1001], signal())
  expect(preview.senses).toHaveLength(10)
  expect(preview.senses.slice(0, 3).map(sense => sense.id)).toEqual([49, 50, 51])
  await services.library.updateDeckSenses('everyday', { add: [49, 50], remove: [] }, signal())
  await services.library.updateDeckSenses('everyday', { add: [49], remove: [50] }, signal())
  expect((await services.library.meanings('everyday', { q: 'run' }, signal())).senses.map(sense => sense.sense_id)).toEqual([49])
  const created = await services.library.createDeck('preview-personal', 'Verbs', [51], signal())
  expect((await services.dictionary.context(1001, signal())).senses.find(sense => sense.sense_id === 51)?.decks).toContainEqual({ id: created, name: 'Verbs', owner_id: 'preview-alex', space: 'personal' })
  const orbit = (await services.dictionary.search('orbit', signal())).items[0]
  expect(orbit.kind).toBe('reference')
  if (orbit.kind !== 'reference') throw new Error('Expected an ungenerated reference')
  const job = await services.dictionary.prepare(orbit.reference_id, orbit.display, signal())
  await services.dictionary.generation(job.task_id, signal())
  expect((await services.dictionary.generation(job.task_id, signal())).status).toBe('succeeded')
  expect((await services.dictionary.search('orbit', signal())).items[0]).toMatchObject({ kind: 'word', word_id: 1002, match_kind: 'exact' })
})

test('invented lexical fixture follows Word and Sense DTOs', () => {
  const words = database.dictionary.words.map(parseDictionaryWord)
  const pending = database.dictionary.pending_words.map(parseDictionaryWord)
  expect(words).toHaveLength(52)
  expect(words.find(word => word.lemma === 'run')?.senses).toHaveLength(10)
  expect(words.find(word => word.lemma === 'bank')?.senses).toHaveLength(5)
  expect(words.find(word => word.lemma === 'light')?.senses.map(sense => sense.pos)).toContain('adjective')
  expect(pending.find(word => word.lemma === 'orbit')?.senses).toHaveLength(3)
  const senses = [...words, ...pending].flatMap(word => word.senses)
  expect([...database.dictionary.words, ...database.dictionary.pending_words].every(word => word.senses.every(sense => !('usage_note' in sense)))).toBe(true)
  expect(senses.every(sense => !('usage_note' in sense))).toBe(true)
  expect(new Set(senses.map(sense => sense.id)).size).toBe(senses.length)
  expect(senses.every(sense => sense.definition && sense.examples.length > 0 && sense.tier)).toBe(true)
})

const focusSignal = new AbortController().signal

test('preparation supports every selected public type, one format and K up to three', async () => {
  const services = createMockServices({ latency: 0 })
  const types = services.account.initialProfile!.settings.learning.question_types
  for (const type of types) {
    await services.account.updateSettings({ learning: { question_types: [type], formats: ['single_choice'], questions_per_sense: 3, max_sense_count: 1 } }, focusSignal)
    const prepared = await services.learning.prepare({ node_id: 'everyday', selection: 'new' }, focusSignal)
    expect(prepared.actual_question_count).toBe(3)
    for (const item of prepared.bundles[0].questions) {
      expect(item.question.question_type).toBe(type)
      expect(item.options).toHaveLength(4)
      expect(new Set(item.options.map(option => option.id)).size).toBe(4)
    }
  }
  await expect(services.learning.prepare({ node_id: 'everyday', selection: 'new', max_sense_count: 21 }, focusSignal)).rejects.toMatchObject({ status: 422 })
})

test('public account contract omits private settings and supports bio before a handle', async () => {
  const fixture = structuredClone(database)
  Object.assign(fixture.account, { handle: null })
  const services = createMockServices({ database: fixture, latency: 0 })
  const signal = new AbortController().signal
  expect(await services.account.publicProfile('preview-alex', signal)).not.toHaveProperty('settings')
  await expect(services.library.publicContents('preview-personal', undefined, signal)).rejects.toMatchObject({ status: 404 })
  const edited = await services.account.updateProfile({ bio: 'A public introduction.' }, signal)
  expect(edited.handle).toBeNull()
  expect((await services.account.publicProfile('preview-alex', signal)).bio).toBe('A public introduction.')
})
