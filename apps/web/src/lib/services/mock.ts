import database from './mock/database.json' with { type: 'json' }
import type { AccountProfile } from '../api'
import { HomeApiError, parseActivity, parseLibrary, parseSchedule, parseSummary } from '../home-api'
import { eventCount, reportingDay, shiftDay } from '../home-calendar'
import type { DateWindow, FrontendServices } from './contracts'
import { createMockLibrary } from './mock/library'
import { createMockDictionary } from './mock/dictionary'
import { createMockQuestions } from './mock/questions'

export type MockDatabase = typeof database
type MockOptions = { database?: MockDatabase; now?: () => Date; latency?: number }

export function createMockServices(options: MockOptions = {}): FrontendServices {
  // Isolate each adapter instance; callers never receive the mutable seed object.
  const db = structuredClone(options.database ?? database)
  const now = options.now ?? (() => new Date())
  const profile = db.account as AccountProfile
  const library = createMockLibrary(db, now)
  const dictionary = createMockDictionary(db, now, library.details)
  const questions = createMockQuestions(db, library, now)
  const today = () => reportingDay(now(), profile.settings!.timezone)
  const asOf = () => now().toISOString()
  const summary = (id?: string) => {
    return parseSummary(library.summary(id ?? profile.library_node_id))
  }
  const dates = (window: DateWindow) => {
    const length = Math.round((Date.parse(`${window.end}T00:00:00Z`) - Date.parse(`${window.start}T00:00:00Z`)) / 86400000) + 1
    if (!Number.isInteger(length) || length < 1 || length > 366) throw new HomeApiError(422, 'invalid_date_window')
    return Array.from({ length }, (_, index) => shiftDay(window.start, index))
  }
  async function respond<T>(read: () => T, signal: AbortSignal): Promise<T> {
    if (signal.aborted) throw signal.reason ?? new DOMException('Cancelled', 'AbortError')
    await new Promise<void>((resolve, reject) => {
      const abort = () => { clearTimeout(timer); reject(signal.reason ?? new DOMException('Cancelled', 'AbortError')) }
      const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve() }, options.latency ?? 100)
      signal.addEventListener('abort', abort, { once: true })
    })
    if (signal.aborted) throw signal.reason ?? new DOMException('Cancelled', 'AbortError')
    return structuredClone(read())
  }
  return {
    mode: 'mock', notice: 'Design preview · Sample data · Nothing is saved to your account',
    assistant: null,
    account: { initialProfile: structuredClone(profile), profile: signal => respond(() => profile, signal),
      usage: signal => respond(() => ({ period_start: new Date(Date.UTC(now().getUTCFullYear(), now().getUTCMonth(), 1)).toISOString(), period_end: new Date(Date.UTC(now().getUTCFullYear(), now().getUTCMonth() + 1, 1)).toISOString(), allowance_units: 1000, used_units: 0, remaining_units: 1000 }), signal),
      publicProfile: (identifier, signal) => respond(() => {
        const user = [profile, ...db.public_users].find(user => user.id === identifier || user.handle === identifier.toLowerCase())
        if (!user) throw new HomeApiError(404, 'account_not_found')
        return { id: user.id, display_name: user.display_name, handle: user.handle, bio: user.bio, joined_at: user.joined_at, published_node_id: user.published_node_id }
      }, signal),
      updateProfile: (patch, signal) => respond(() => {
        if (patch.handle !== undefined) {
          const handle = patch.handle.trim().toLowerCase()
          if (!/^[a-z][a-z0-9_]{2,29}$/.test(handle)) throw new HomeApiError(422, 'invalid_handle')
          if (db.public_users.some(user => user.handle === handle)) throw new HomeApiError(409, 'handle_unavailable')
          profile.handle = handle
        }
        if (patch.bio !== undefined) {
          if (patch.bio !== null && patch.bio.trim().length > 500) throw new HomeApiError(422, 'invalid_bio')
          profile.bio = patch.bio?.trim() ?? null
        }
        return profile
      }, signal),
      updateSettings: (patch, signal) => respond(() => {
        const learning = { ...profile.settings.learning, ...patch.learning }
        const options = profile.learning_options
        if (patch.learning?.formats?.some(format => format !== 'SINGLE_CHOICE' && !options.advanced_grading)) throw new HomeApiError(403, 'advanced_grading_not_available')
        if (learning.question_types.length === 0 || learning.formats.length === 0) throw new HomeApiError(422, 'invalid_preferences')
        if (!learning.question_types.some(type => learning.formats.some(format => options.pairs.some(pair => pair.question_type === type && pair.format === format))) ||
          learning.questions_per_sense < options.limits.min_questions_per_sense || learning.questions_per_sense > options.limits.max_questions_per_sense ||
          learning.questions_per_sense * learning.max_sense_count > options.limits.max_questions_per_prepare) throw new HomeApiError(422, 'invalid_preferences')
        profile.settings = { ...profile.settings, ...patch, learning }
        profile.effective_learning = learning
        profile.learning_restriction = null
        return profile
      }, signal) },
    learning: {
      summary: (id, signal) => respond(() => summary(id), signal),
      activity: (window, signal) => respond(() => {
        const events = new Map(db.activity.days.map(day => [shiftDay(today(), -day.days_ago), day]))
        const days = dates(window).map(day => ({ day, applied_events: events.get(day)?.applied_events ?? 0, practice_events: events.get(day)?.practice_events ?? 0 }))
        let currentStreak = 0
        let cursor = eventCount(events.get(today()) ?? { applied_events: 0, practice_events: 0 }) ? today() : shiftDay(today(), -1)
        while (events.has(cursor) && eventCount(events.get(cursor)!) > 0) { currentStreak++; cursor = shiftDay(cursor, -1) }
        return parseActivity({ as_of: asOf(), timezone: profile.settings!.timezone, start_date: window.start, end_date: window.end, days,
          current_streak: currentStreak, longest_streak: Math.max(currentStreak, db.activity.longest_streak),
          applied_events: days.reduce((sum, day) => sum + day.applied_events, 0), practice_events: days.reduce((sum, day) => sum + day.practice_events, 0) })
      }, signal),
      schedule: (window, signal) => respond(() => {
        const scheduled = new Map(db.schedule.map(day => [shiftDay(today(), day.days_ahead), day.count]))
        return parseSchedule({ node_id: profile.library_node_id, as_of: asOf(), timezone: profile.settings!.timezone, start_date: window.start, end_date: window.end,
          days: dates(window).map(day => ({ day, count: scheduled.get(day) ?? 0 })) })
      }, signal),
      prepare: (input, signal) => respond(() => questions.prepare(input, profile.effective_learning!), signal),
      grade: (input, signal) => respond(() => {
        if (!profile.learning_options.advanced_grading) throw new HomeApiError(403, 'advanced_grading_not_available')
        return questions.grade(input)
      }, signal),
      review: (input, signal) => respond(() => questions.review(input), signal),
    },
    library: {
      discovery: (options, signal) => respond(() => library.discovery(options), signal),
      sources: (id, senseId, cursor, signal) => respond(() => library.sources(id, senseId, cursor), signal),
      createReference: (parentId, targetId, name, signal) => respond(() => library.createReference(parentId, targetId, name), signal),
      list: (parentId, signal) => respond(() => parseLibrary(library.contents(parentId, { limit: 4 })), signal),
      publicContents: (parentId, cursor, signal) => respond(() => {
        if (library.details(parentId).space !== 'PUBLISHED') throw new HomeApiError(404, 'node_not_found')
        const page = library.contents(parentId, { cursor, limit: 12 })
        return parseLibrary({ ...page, nodes: page.nodes.map(node => ({ ...node, summary: null })) })
      }, signal),
      publicNode: (nodeId, signal) => respond(() => {
        const detail = library.details(nodeId)
        if (detail.space !== 'PUBLISHED') throw new HomeApiError(404, 'node_not_found')
        return { ...detail, summary: null }
      }, signal),
      publicMeanings: (nodeId, cursor, signal) => respond(() => {
        if (library.details(nodeId).space !== 'PUBLISHED') throw new HomeApiError(404, 'node_not_found')
        const page = library.meanings(nodeId, { cursor, limit: 12 })
        return { ...page, senses: page.senses.map(sense => ({ ...sense, learning: null, sources: [], sources_has_more: false })) }
      }, signal),
      details: (id, signal) => respond(() => library.details(id), signal),
      contents: (id, options, signal) => respond(() => library.contents(id, options), signal),
      meanings: (id, options, signal) => respond(() => library.meanings(id, options), signal),
      updateDeckSenses: (id, change, signal) => respond(() => library.updateDeckSenses(id, change), signal),
      createDeck: (parentId, name, senseIds, signal) => respond(() => library.createDeck(parentId, name, senseIds), signal),
      createNode: (input, signal) => respond(() => library.createNode(input.parentId, input.type, input.name, input.description), signal),
      updateNode: (id, change, signal) => respond(() => library.updateNode(id, change), signal),
      moveNode: (id, parentId, signal, publication) => respond(() => library.moveNode(id, parentId, publication), signal),
      copyNode: (id, parentId, signal) => respond(() => library.copyNode(id, parentId), signal),
      deleteNode: (id, signal) => respond(() => library.deleteNode(id), signal),
    },
    dictionary: {
      search: (query, signal) => respond(() => dictionary.search(query), signal),
      word: (id, signal) => respond(() => dictionary.word(id), signal),
      previews: (ids, signal) => respond(() => dictionary.previews(ids), signal),
      context: (id, signal) => respond(() => dictionary.context(id), signal),
      prepare: (id, target, signal) => respond(() => dictionary.prepare(id, target), signal),
      generation: (id, signal) => respond(() => dictionary.generation(id), signal),
    },
  }
}
