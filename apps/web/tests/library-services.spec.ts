import { expect, test } from '@playwright/test'
import { createMockServices } from '../src/lib/services/mock'
import database from '../src/lib/services/mock/database.json' with { type: 'json' }
import { libraryHref, publishedHref } from '../src/lib/library-model'
import { parseMeaningPage, parseNodeDetails } from '../src/lib/library-api'
import { createHttpServices } from '../src/lib/services/http'
import { libraryNodeKind } from '../src/lib/library-model'
import { flashcardArtwork, flashcardBackgrounds } from '../src/lib/flashcard-artwork'
import { parseMarkedText, targetInflections } from '../src/lib/marked-text'
import { backgroundCanvas } from '../src/lib/background-layout'
import { parseDictionaryWord } from '../src/lib/dictionary-model'

const signal = () => new AbortController().signal
const now = () => new Date('2026-10-07T02:00:00Z')

test('adaptive background canvases fill arbitrary ratios without cropping or x/y distortion', () => {
  for (const [width, height] of [[400, 240], [1200, 200], [760, 360], [320, 500], [240, 240]]) {
    const canvas = backgroundCanvas(width, height)
    expect(canvas.width).toBeGreaterThanOrEqual(400)
    expect(canvas.height).toBeGreaterThanOrEqual(240)
    expect(canvas.width / canvas.height).toBeCloseTo(width / height, 8)
    expect(width / canvas.width).toBeCloseTo(height / canvas.height, 8)
  }
  expect(backgroundCanvas(0, 0)).toEqual({ width: 400, height: 240 })
})

test('flashcard seeds select only the existing 16 backgrounds, independent of order or deck', () => {
  const senses = database.dictionary.words.map(parseDictionaryWord).flatMap(word => word.senses)
  const artwork = senses.map(sense => flashcardArtwork(sense.id))
  expect(flashcardBackgrounds).toHaveLength(16)
  expect(new Set(flashcardBackgrounds).size).toBe(16)
  expect(new Set(artwork).size).toBeGreaterThan(1)
  for (const sense of [...senses].reverse()) {
    expect(flashcardArtwork(sense.id)).toEqual(artwork[senses.indexOf(sense)])
    expect(flashcardArtwork(String(sense.id))).toEqual(flashcardArtwork(sense.id))
    expect(flashcardBackgrounds).toContain(flashcardArtwork(sense.id))
  }
  const deckLimit = Array.from({ length: 1000 }, (_, index) => flashcardArtwork(index + 1))
  expect(new Set(deckLimit).size).toBe(16)
})

test('marked text follows backend inflections, repeated/discontinuous targets and Unicode', () => {
  for (const inf of targetInflections) {
    for (const label of [inf, inf.toUpperCase()]) {
      const parsed = parseMarkedText(`Before <T inf="${label}">Target</T> after.`)
      expect(parsed).toEqual({ valid: true, text: 'Before Target after.', spans: [{ surface: 'Target', inf, start: 7, end: 13 }] })
    }
  }
  const split = parseMarkedText('She <t inf="past">gave</t> it <t inf="base">up</t>, then <t inf="past">gave up</t> again.')
  expect(split.text).toBe('She gave it up, then gave up again.')
  expect(split.spans.map(span => span.surface)).toEqual(['gave', 'up', 'gave up'])
  const unicode = parseMarkedText('🌍 <t inf="base">café</t> — café.')
  expect(unicode.spans.map(span => unicode.text.slice(span.start, span.end))).toEqual(['café'])
  expect(parseMarkedText('a word with no markup')).toEqual({ text: 'a word with no markup', spans: [], valid: true })
  for (const sense of database.dictionary.words.map(parseDictionaryWord).flatMap(word => word.senses)) {
    const parsed = parseMarkedText(sense.examples[0].content)
    expect(parsed.valid).toBe(true)
    expect(parsed.spans.length).toBeGreaterThan(0)
  }
})

test('malformed markup remains literal, without partially trusted targets or HTML execution', () => {
  const invalid = ['<t inf="unknown">word</t>', '<t inf="base"> </t>', '<t inf="base">word',
    '<t inf="base"><b>word</b></t>', '<t inf="base" onclick="alert(1)">word</t>', '<t inf="base">good</t><t>bad</t>', 'x'.repeat(16001)]
  for (const text of invalid) expect(parseMarkedText(text)).toEqual({ text, spans: [], valid: false })
  const html = '<script>alert(1)</script> <img src=x onerror=alert(1)>'
  expect(parseMarkedText(html)).toEqual({ text: html, spans: [], valid: true }) // Rendered as React text, never HTML.
})

test('live lexical examples read native content and retain backend target markup', () => {
  const content = 'They <t inf="past">abandoned</t> the car.'
  const page = parseMeaningPage({ senses: [{ sense_id: 8, lemma: 'abandon', pos: 'VERB', definition: 'to leave permanently', cefr_level: 'B1',
    learning: null, examples: [{ id: 91, content, theme_id: null }], sources: [], sources_has_more: false }], next_cursor: null })
  expect(page.senses[0].examples).toEqual([{ text: content }])
})

test('Library mock is canonical, scoped, deduplicated and consistent with Home', async () => {
  const service = createMockServices({ latency: 0, now })
  const root = await service.library.details(database.account.library_node_id, signal())
  expect(root.summary).toMatchObject(database.summary)
  const home = await service.learning.summary(undefined, signal())
  expect(home).toMatchObject({ total: root.summary!.total, due: root.summary!.due, new: root.summary!.new, not_due: root.summary!.not_due })
  const folder = await service.library.details('business', signal())
  const children = await service.library.contents('business', {}, signal())
  expect(children.nodes.map(node => node.name)).toEqual(['Meetings', 'Emails', 'Presentations', 'Business Core', 'Workplace Verbs'])
  const meanings = await service.library.meanings('business', { limit: 100 }, signal())
  expect(meanings.senses).toHaveLength(folder.summary!.total)
  expect(new Set(meanings.senses.map(sense => sense.sense_id)).size).toBe(folder.summary!.total)
  expect(meanings.senses.filter(sense => sense.learning!.state === 'DUE')).toHaveLength(folder.summary!.due)
  expect(meanings.senses.filter(sense => sense.learning!.state === 'NEW')).toHaveLength(folder.summary!.new)
  const agenda = meanings.senses.find(sense => sense.lemma === 'agenda')!
  expect(agenda.sources.map(source => source.id).sort()).toEqual(['business-core', 'meeting-expressions'])
  expect(folder.breadcrumbs.map(node => node.name)).toEqual(['My Library', 'Personal'])
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
  const due = await service.library.meanings('everyday', { state: 'DUE' }, signal())
  expect(due.senses.every(sense => sense.learning!.state === 'DUE')).toBe(true)
  const reviewed = await service.library.meanings('everyday', { sort: 'LAST_REVIEWED_DESC', limit: 100 }, signal())
  const dates = reviewed.senses.map(sense => sense.learning!.last_reviewed_at ?? '')
  expect(dates).toEqual([...dates].sort().reverse())
  const search = await service.library.contents('business', { q: 'Email' }, signal())
  expect(search.nodes.some(node => node.id === 'email-expressions')).toBe(true)
  expect(search.nodes.some(node => node.id === 'travel-source')).toBe(false)
})

test('references preserve placement but resolve readable sources; missing targets expose no contents', async () => {
  const service = createMockServices({ latency: 0, now })
  const reference = await service.library.details('travel', signal())
  const source = await service.library.details('travel-source', signal())
  expect(reference.owner_id).toBe(database.account.id)
  expect(source.owner_id).not.toBe(database.account.id)
  expect(reference.target?.id).toBe(source.id)
  expect(reference.summary!.total).toBe(source.summary!.total)
  expect(source.breadcrumbs).toEqual([{ id: 'preview-sam-published', name: 'Published' }])
  expect((await service.library.meanings('travel', {}, signal())).senses.map(sense => sense.sense_id)).toEqual((await service.library.meanings('travel-source', {}, signal())).senses.map(sense => sense.sense_id))
  expect((await service.library.contents(database.account.personal_node_id, {}, signal())).nodes.find(node => node.id === 'travel')?.target_type).toBe('DECK')
  const savedBusiness = await service.library.details('saved-business', signal())
  expect(savedBusiness.target).toMatchObject({ id: 'business', type: 'FOLDER' })
  expect(savedBusiness.summary).toMatchObject(database.nodes.find(node => node.id === 'saved-business')!.counts)
  expect((await service.library.contents('saved-business', {}, signal())).nodes.map(node => node.id)).toEqual((await service.library.contents('business', {}, signal())).nodes.map(node => node.id))
  expect((await service.library.meanings('saved-business', { limit: 100 }, signal())).senses.map(sense => sense.sense_id)).toEqual((await service.library.meanings('business', { limit: 100 }, signal())).senses.map(sense => sense.sense_id))
  const emails = await service.library.contents('emails', {}, signal())
  const folderReference = emails.nodes.find(node => node.id === 'saved-meetings')!
  expect(libraryNodeKind(folderReference)).toBe('FOLDER')
  expect((await service.library.details(folderReference.id, signal())).target?.type).toBe('FOLDER')
  expect((await service.library.contents(folderReference.id, {}, signal())).nodes.map(node => node.id)).toEqual(['meeting-expressions'])
  const unavailable = await service.library.details('unavailable-reference', signal())
  expect(unavailable.target).toBeNull()
  expect(unavailable.reference_available).toBe(false)
  expect(unavailable.summary).toBeNull()
  await expect(service.library.meanings(unavailable.id, {}, signal())).rejects.toMatchObject({ code: 'reference_unavailable' })
  await expect(service.library.details('not-a-node', signal())).rejects.toMatchObject({ status: 404 })
})

test('live list adapter resolves reference types through readable endpoints, deduplicates targets and never guesses missing ones', async () => {
  const original = globalThis.fetch
  const requests: string[] = []
  const details = { id: 'source-folder', name: 'Readable folder', type: 'FOLDER', space: 'PUBLISHED', owner_id: 'owner', role: 'NORMAL', description: null,
    created_at: now().toISOString(), updated_at: now().toISOString(), breadcrumbs: [], reference_id: null, reference_available: null }
  const reference = (id: string, reference_id: string) => ({ id, name: id, type: 'REFERENCE', description: null, summary: null, reference_id })
  globalThis.fetch = async (url, init) => {
    requests.push(String(url))
    expect(init?.headers).toEqual({ Authorization: 'Bearer test-token' })
    if (String(url).startsWith('/api/v1/nodes?')) return new Response(JSON.stringify({ nodes: [reference('first', 'source-folder'), reference('second', 'source-folder'), reference('unavailable', 'hidden-source')], next_cursor: 'page-2' }))
    if (String(url) === '/api/v1/nodes/source-folder') return new Response(JSON.stringify(details))
    return new Response(JSON.stringify({ error: 'node_not_found' }), { status: 404 })
  }
  try {
    const result = await createHttpServices(async () => 'test-token').library.list('parent', signal())
    expect(result.nodes.map(node => node.target_type)).toEqual(['FOLDER', 'FOLDER', null])
    expect(result.nodes[2].reference_id).toBeNull()
    expect(result.next_cursor).toBe('page-2')
    expect(requests.filter(path => path === '/api/v1/nodes/source-folder')).toHaveLength(1)
    expect(requests).toHaveLength(3)
  } finally { globalThis.fetch = original }
})

test('empty decks, cancellation and returned-object isolation preserve seed content', async () => {
  const service = createMockServices({ latency: 0, now })
  const empty = await service.library.details('empty-deck', signal())
  expect(empty.summary!.total).toBe(0)
  expect((await service.library.meanings('empty-deck', {}, signal())).senses).toEqual([])
  const result = await service.library.details('everyday', signal())
  result.name = 'Changed'
  expect((await service.library.details('everyday', signal())).name).toBe('Everyday conversation')
  const controller = new AbortController()
  controller.abort()
  await expect(service.library.meanings('everyday', {}, controller.signal)).rejects.toBeDefined()
})

test('Library contracts reject incomplete DTOs and links safely encode node identities', () => {
  expect(() => parseNodeDetails({ id: 'node' })).toThrow()
  expect(() => parseMeaningPage({ senses: [{ sense_id: -1 }], next_cursor: null })).toThrow()
  expect(() => parseMeaningPage({ senses: [{ sense_id: 1, lemma: 'bank', pos: 'noun', definition: 'a bank', learning: { state: 'MASTERED' } }], next_cursor: null })).toThrow()
  expect(libraryHref('a&tab=bad', 'words')).toBe('/app/personal/a%26tab%3Dbad/words')
  expect(libraryHref('a/b?#', 'overview')).toBe('/app/personal/a%2Fb%3F%23')
  expect(libraryHref('everyday')).toBe('/app/personal/everyday')
  expect(libraryHref('everyday', 'overview')).toBe('/app/personal/everyday')
  expect(libraryHref()).toBe('/app/personal')
  expect(publishedHref('a/b', 'node ?', 'words')).toBe('/app/u/a%2Fb/published/node%20%3F/words')
  expect(parseMeaningPage({ senses: [], next_cursor: null }).senses).toEqual([])
})
