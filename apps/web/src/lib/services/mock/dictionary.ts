import type { MockDatabase } from '../mock'
import { parseDictionaryWord, type DictionaryWord, type WordContext, type WordGeneration, type WordSearch } from '../../dictionary-model'
import { HomeApiError } from '../../home-api'

export function createMockDictionary(db: MockDatabase, now: () => Date) {
  const words = new Map<number, DictionaryWord>(db.dictionary.words.map(entry => [entry.id, parseDictionaryWord(entry)]))
  const readyWords = db.dictionary.words as DictionaryWord[]
  const pending = new Map(db.dictionary.pending_words.map(entry => [entry.lemma, parseDictionaryWord(entry)]))
  const jobs = new Map<string, { result: WordGeneration; polls: number; word: DictionaryWord }>()

  function search(query: string): WordSearch {
    const key = query.trim().toLowerCase()
    if (!key || key.length > 512) throw new HomeApiError(422, 'invalid_lexical_query')
    const hits = [...words.values()].flatMap(word => {
      const surfaces = [{ text: word.lemma, kind: 'LEMMA' }, ...word.aliases.map(text => ({ text, kind: 'ALIAS' })),
        ...word.senses.flatMap(sense => sense.forms.map(form => ({ text: form.surface, kind: 'FORM' })))]
      const match = surfaces.find(surface => surface.text.toLowerCase() === key)
        ?? surfaces.find(surface => surface.text.toLowerCase().startsWith(key))
        ?? surfaces.find(surface => surface.text.toLowerCase().includes(key))
      return match ? [{ word_id: word.id, lemma: word.lemma, entry_type: word.type,
        match_kind: match.text.toLowerCase() === key ? match.kind : match.text.toLowerCase().startsWith(key) ? 'PREFIX' : 'SUBSTRING',
        matched_surface: match.text }] : []
    }).sort((a, b) => Number(b.matched_surface.toLowerCase() === key) - Number(a.matched_surface.toLowerCase() === key) || a.lemma.localeCompare(b.lemma))
    return { words: hits.slice(0, 30), available: db.dictionary.available.filter(hit =>
      hit.display.toLowerCase().includes(key) && !words.has(pending.get(hit.display)?.id ?? -1)) }
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
      const decks = Object.entries(memberships).filter(([, ids]) => ids.includes(sense.id)).map(([deckId]) => ({ id: deckId, name: names.get(deckId) ?? deckId }))
      const state = due.has(sense.id) ? 'DUE' : fresh.has(sense.id) || sense.id > 48 ? 'NEW' : 'NOT_YET_DUE'
      return { sense_id: sense.id, learning: { state: state as 'DUE' | 'NEW' | 'NOT_YET_DUE', due_at: null, last_reviewed_at: null },
        decks, deck_count: decks.length, decks_has_more: false }
    })
    const dueCount = senses.filter(sense => sense.learning.state === 'DUE').length
    const newCount = senses.filter(sense => sense.learning.state === 'NEW').length
    return { as_of: now().toISOString(), senses, total: senses.length, studied: senses.length - newCount,
      new: newCount, due: dueCount, not_due: senses.length - newCount - dueCount }
  }
  function prepare(availableId: string, target: string): WordGeneration {
    const hit = db.dictionary.available.find(hit => hit.available_id === availableId && hit.display === target)
    const candidate = hit && pending.get(hit.display)
    if (!candidate) throw new HomeApiError(422, 'invalid_generation_selection')
    const existing = [...jobs.values()].find(job => job.word.id === candidate.id)
    if (existing) return existing.result
    const generationId = crypto.randomUUID()
    const result: WordGeneration = { generation_id: generationId, status: 'QUEUED', word_id: null,
      stage: null, error: null, status_url: `/api/v1/word-generations/${generationId}` }
    jobs.set(generationId, { result, polls: 0, word: candidate })
    return result
  }
  function generation(id: string): WordGeneration {
    const job = jobs.get(id)
    if (!job) throw new HomeApiError(404, 'generation_not_found')
    if (job.result.status === 'SUCCEEDED') return job.result
    job.polls++
    if (job.polls === 1) job.result = { ...job.result, status: 'RUNNING', stage: 'Preparing entry' }
    else {
      words.set(job.word.id, job.word)
      readyWords.push(job.word)
      job.result = { ...job.result, status: 'SUCCEEDED', word_id: job.word.id, stage: null }
    }
    return job.result
  }
  return { search, word, previews, context, prepare, generation }
}
