import type { LibraryDetails } from '../../library-model'
import type { MockDatabase } from '../mock'
import { MatchKind, parseDictionaryWord, type DictionaryWord, type WordContext, type WordGeneration, type WordHit, type WordSearch } from '../../dictionary-model'
import { HomeApiError } from '../../home-api'

export function createMockDictionary(db: MockDatabase, now: () => Date, details: (id: string) => LibraryDetails) {
  const words = new Map<number, DictionaryWord>(db.dictionary.words.map(entry => [entry.id, parseDictionaryWord(entry)]))
  const readyWords = db.dictionary.words as DictionaryWord[]
  const pending = new Map(db.dictionary.pending_words.map(entry => [entry.lemma, parseDictionaryWord(entry)]))
  const jobs = new Map<string, { result: WordGeneration; polls: number; word: DictionaryWord }>()

  function search(query: string): WordSearch {
    const normalize = (surface: string) => surface.normalize('NFKC').trim().replace(/\s+/g, ' ').toLowerCase()
    const key = normalize(query)
    if (!key || key.length > 512) throw new HomeApiError(422, 'invalid_lexical_query')
    const hits = [...words.values()].flatMap<{ hit: WordHit; surfaceRank: number }>(word => {
      const surfaces = [
        { content: word.lemma, rank: 0 },
        ...word.aliases.map(content => ({ content, rank: 1 })),
        ...word.senses.flatMap(sense => sense.forms.map(form => ({ content: form.surface, rank: 2 }))),
      ]
      const match = surfaces.find(surface => normalize(surface.content) === key)
        ?? surfaces.find(surface => normalize(surface.content).startsWith(key))
        ?? surfaces.find(surface => normalize(surface.content).includes(key))
      return match ? [{ surfaceRank: match.rank, hit: { kind: 'word', word_id: word.id, lemma: word.lemma, entry_type: word.type,
        match_kind: normalize(match.content) === key ? MatchKind.EXACT : normalize(match.content).startsWith(key) ? MatchKind.PREFIX : MatchKind.SUBSTRING,
        matched_surface: match.content } }] : []
    })
    const references = db.dictionary.references.filter(hit =>
      normalize(hit.display).includes(key) && !words.has(pending.get(hit.display)?.id ?? -1)).map(hit => ({ surfaceRank: 0, hit: {
        ...hit, kind: 'reference' as const, matched_surface: hit.display,
        match_kind: normalize(hit.display) === key ? MatchKind.EXACT : normalize(hit.display).startsWith(key) ? MatchKind.PREFIX : MatchKind.SUBSTRING,
      } }))
    const ranks = Object.values(MatchKind)
    return { items: [...hits, ...references].sort(({ hit: a, surfaceRank: ar }, { hit: b, surfaceRank: br }) =>
      ranks.indexOf(a.match_kind) - ranks.indexOf(b.match_kind)
      || Number(a.kind === 'reference') - Number(b.kind === 'reference')
      || ar - br
      || normalize(a.kind === 'word' ? a.lemma : a.display).localeCompare(normalize(b.kind === 'word' ? b.lemma : b.display))
      || (a.kind === 'word' && b.kind === 'word' ? a.word_id - b.word_id : a.kind === 'reference' && b.kind === 'reference' ? a.reference_id.localeCompare(b.reference_id) : 0))
      .slice(0, 30).map(item => item.hit) }
  }
  function word(id: number) {
    const value = words.get(id)
    if (!value) throw new HomeApiError(404, 'word_not_found')
    return value
  }
  function previews(ids: number[]) {
    if (!ids.length || ids.length > 30 || new Set(ids).size !== ids.length) throw new HomeApiError(422, 'lexical_batch_too_large')
    const values = ids.map(word)
    if (values.reduce((total, entry) => total + entry.senses.length, 0) > 500) throw new HomeApiError(422, 'lexical_batch_too_large')
    return values.map(entry => ({ word_id: entry.id, lemma: entry.lemma, entry_type: entry.type,
      senses: entry.senses.map(sense => ({ ...sense, examples: sense.examples.slice(0, 2) })) }))
  }
  function context(id: number): WordContext {
    const value = word(id)
    if (value.senses.length > 100) throw new HomeApiError(422, 'context_too_large')
    const due = new Set(db.library.due_sense_ids), fresh = new Set(db.library.new_sense_ids)
    const names = new Map([...db.nodes, ...db.library.nodes].map(node => [node.id, node.name]))
    const memberships = db.library.membership as Record<string, number[]>
    const senses = value.senses.map(sense => {
      const decks = Object.entries(memberships).filter(([, ids]) => ids.includes(sense.id)).map(([deckId]) => ({ id: deckId, name: names.get(deckId) ?? deckId, owner_id: details(deckId).owner_id, space: details(deckId).space as 'personal' | 'published' }))
      const state = due.has(sense.id) ? 'due' : fresh.has(sense.id) || sense.id > 48 ? 'new' : 'not_yet_due'
      return { sense_id: sense.id, learning: { state: state as 'due' | 'new' | 'not_yet_due', due_at: null, last_reviewed_at: null },
        decks, deck_count: decks.length, decks_has_more: false }
    })
    const dueCount = senses.filter(sense => sense.learning.state === 'due').length
    const newCount = senses.filter(sense => sense.learning.state === 'new').length
    return { as_of: now().toISOString(), senses, total: senses.length, studied: senses.length - newCount,
      new: newCount, due: dueCount, not_due: senses.length - newCount - dueCount }
  }
  function prepare(referenceId: string, target: string): WordGeneration {
    const hit = db.dictionary.references.find(hit => hit.reference_id === referenceId && hit.display === target)
    const candidate = hit && pending.get(hit.display)
    if (!candidate) throw new HomeApiError(422, 'invalid_generation_selection')
    const existing = [...jobs.values()].find(job => job.word.id === candidate.id)
    if (existing) return existing.result
    const generationId = crypto.randomUUID()
    const result: WordGeneration = { task_id: generationId, status: 'running', word_id: null,
      stage: null, error: null, status_url: `/v1/word-tasks/${generationId}` }
    jobs.set(generationId, { result, polls: 0, word: candidate })
    return result
  }
  function generation(id: string): WordGeneration {
    const job = jobs.get(id)
    if (!job) throw new HomeApiError(404, 'generation_not_found')
    if (job.result.status === 'succeeded') return job.result
    job.polls++
    if (job.polls === 1) job.result = { ...job.result, status: 'running', stage: 'Preparing entry' }
    else {
      words.set(job.word.id, job.word)
      readyWords.push(job.word)
      job.result = { ...job.result, status: 'succeeded', word_id: job.word.id, stage: null }
    }
    return job.result
  }
  return { search, word, previews, context, prepare, generation }
}
