import { HomeApiError } from './home-api'
import type { LearningState } from './library-model'

export type WordHit = { word_id: number; lemma: string; entry_type: string; match_kind: string; matched_surface: string }
export type AvailableHit = { available_id: string; display: string; entry_type: string }
export type WordSearch = { words: WordHit[]; available: AvailableHit[] }
export type DictionaryText = { id: number; content: string; theme_id: number | null }
export type DictionaryRelation = { rel_type: string; to_word_id: number; to_word_lemma: string; resolution_state: string; to_sense_id: number | null }
export type DictionarySense = {
  id: number; word_id: number; pos: string; tier: string; definition: DictionaryText | null; examples: DictionaryText[]
  forms: { surface: string; inf: string }[]; patterns: string[]; collocations: string[]; relations: DictionaryRelation[]
  cefr_level: string | null; register: string | null; usage_note: string | null; ipa_uk: string | null; ipa_us: string | null
}
export type DictionaryWord = {
  id: number; lemma: string; type: string; generation_state: string; senses: DictionarySense[]; aliases: string[]
  related: { rel_type: string; to_word_id: number; to_word_lemma: string }[]
}
export type WordPreview = { word_id: number; lemma: string; entry_type: string; senses: DictionarySense[] }
export type SenseContext = { sense_id: number; learning: { state: LearningState; due_at: string | null; last_reviewed_at: string | null }; decks: { id: string; name: string }[]; deck_count: number; decks_has_more: boolean }
export type WordContext = { as_of: string; senses: SenseContext[]; total: number; studied: number; new: number; due: number; not_due: number }
export type WordGeneration = { generation_id: string; status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED'; word_id: number | null; stage: string | null; error: string | null; status_url: string }

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new HomeApiError(502, 'invalid_response')
  return value as Record<string, unknown>
}
function array(value: unknown): unknown[] { if (!Array.isArray(value)) throw new HomeApiError(502, 'invalid_response'); return value }
function string(value: unknown): string { if (typeof value !== 'string') throw new HomeApiError(502, 'invalid_response'); return value }
function id(value: unknown): number { if (!Number.isSafeInteger(value) || Number(value) < 1) throw new HomeApiError(502, 'invalid_response'); return Number(value) }
function count(value: unknown): number { if (!Number.isSafeInteger(value) || Number(value) < 0) throw new HomeApiError(502, 'invalid_response'); return Number(value) }
function boolean(value: unknown): boolean { if (typeof value !== 'boolean') throw new HomeApiError(502, 'invalid_response'); return value }
function optional(value: unknown): string | null { return value == null ? null : string(value) }
function nativeText(value: unknown): DictionaryText {
  const item = object(value)
  return { id: id(item.id), content: string(item.content), theme_id: item.theme_id == null ? null : id(item.theme_id) }
}
export function parseDictionarySense(value: unknown): DictionarySense {
  const sense = object(value)
  return { id: id(sense.id), word_id: id(sense.word_id), pos: string(sense.pos), tier: string(sense.tier),
    definition: sense.definition == null ? null : nativeText(sense.definition), examples: array(sense.examples ?? []).map(nativeText),
    forms: array(sense.forms ?? []).map(value => { const form = object(value); return { surface: string(form.surface), inf: string(form.inf) } }),
    patterns: array(sense.patterns ?? []).map(string), collocations: array(sense.collocations ?? []).map(string),
    relations: array(sense.relations ?? []).map(value => { const relation = object(value); return { rel_type: string(relation.rel_type),
      to_word_id: id(relation.to_word_id), to_word_lemma: string(relation.to_word_lemma), resolution_state: string(relation.resolution_state),
      to_sense_id: relation.to_sense_id == null ? null : id(relation.to_sense_id) } }),
    cefr_level: optional(sense.cefr_level), register: optional(sense.register), usage_note: optional(sense.usage_note),
    ipa_uk: optional(sense.ipa_uk), ipa_us: optional(sense.ipa_us) }
}

export function parseWordSearch(value: unknown): WordSearch {
  const result = object(value)
  return {
    words: array(result.words).map(value => { const hit = object(value); return { word_id: id(hit.word_id), lemma: string(hit.lemma), entry_type: string(hit.entry_type), match_kind: string(hit.match_kind), matched_surface: string(hit.matched_surface) } }),
    available: array(result.available).map(value => { const hit = object(value); return { available_id: string(hit.available_id), display: string(hit.display), entry_type: string(hit.entry_type) } }),
  }
}

export function parseDictionaryWord(value: unknown): DictionaryWord {
  const word = object(value)
  const wordId = id(word.id)
  const senses = array(word.senses ?? []).map(parseDictionarySense)
  if (senses.some(sense => sense.word_id !== wordId)) throw new HomeApiError(502, 'invalid_response')
  return { id: wordId, lemma: string(word.lemma), type: string(word.type), generation_state: string(word.generation_state), senses,
    aliases: array(word.aliases ?? []).map(string),
    related: array(word.related ?? []).map(value => { const relation = object(value); return { rel_type: string(relation.rel_type),
      to_word_id: id(relation.to_word_id), to_word_lemma: string(relation.to_word_lemma) } }),
  }
}

export function parseWordPreviews(value: unknown): WordPreview[] {
  return array(value).map(value => {
    const preview = object(value)
    const word = parseDictionaryWord({ id: preview.word_id, lemma: preview.lemma, type: preview.entry_type, generation_state: 'DONE', senses: preview.senses })
    return { word_id: word.id, lemma: word.lemma, entry_type: word.type, senses: word.senses }
  })
}

export function parseWordContext(value: unknown): WordContext {
  const context = object(value)
  return { as_of: string(context.as_of), total: count(context.total), studied: count(context.studied),
    new: count(context.new), due: count(context.due), not_due: count(context.not_due), senses: array(context.senses).map(value => {
    const item = object(value), learning = object(item.learning)
    if (!['NEW', 'DUE', 'NOT_YET_DUE'].includes(string(learning.state))) throw new HomeApiError(502, 'invalid_response')
    return { sense_id: id(item.sense_id), learning: { state: learning.state as LearningState, due_at: optional(learning.due_at), last_reviewed_at: optional(learning.last_reviewed_at) },
      decks: array(item.decks).map(value => { const deck = object(value); return { id: string(deck.id), name: string(deck.name) } }),
      deck_count: count(item.deck_count), decks_has_more: boolean(item.decks_has_more) }
  }) }
}

export function parseWordGeneration(value: unknown): WordGeneration {
  const job = object(value), status = string(job.status)
  if (!['QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED'].includes(status)) throw new HomeApiError(502, 'invalid_response')
  return { generation_id: string(job.generation_id), status: status as WordGeneration['status'], word_id: job.word_id == null ? null : id(job.word_id), stage: optional(job.stage), error: optional(job.error), status_url: string(job.status_url) }
}
