import { HomeApiError, parseSummary } from './home-api'
import type { LibraryDetails, Meaning, MeaningPage, LearningState } from './library-model'

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new HomeApiError(502, 'invalid_response')
  return value as Record<string, unknown>
}
function text(value: unknown): string {
  if (typeof value !== 'string' || !value) throw new HomeApiError(502, 'invalid_response')
  return value
}
function nullable(value: unknown): string | null { return value == null ? null : text(value) }
function timestamp(value: unknown): string { const result = text(value); if (!Number.isFinite(Date.parse(result))) throw new HomeApiError(502, 'invalid_response'); return result }
function list(value: unknown): unknown[] { if (!Array.isArray(value)) throw new HomeApiError(502, 'invalid_response'); return value }

export function parseNodeDetails(value: unknown): LibraryDetails & { reference_id: string | null } {
  const node = record(value)
  if (!['DECK', 'FOLDER', 'REFERENCE'].includes(text(node.type)) || !['PERSONAL', 'PUBLISHED', 'LIBRARY'].includes(text(node.space))) throw new HomeApiError(502, 'invalid_response')
  if (node.reference_available != null && typeof node.reference_available !== 'boolean') throw new HomeApiError(502, 'invalid_response')
  return { id: text(node.id), name: text(node.name), type: node.type as LibraryDetails['type'], description: nullable(node.description),
    owner_id: text(node.owner_id), role: text(node.role), space: node.space as LibraryDetails['space'],
    created_at: timestamp(node.created_at), updated_at: timestamp(node.updated_at), reference_id: nullable(node.reference_id),
    breadcrumbs: list(node.breadcrumbs).map(value => { const item = record(value); return { id: text(item.id), name: text(item.name) } }),
    summary: node.summary == null ? null : parseSummary(node.summary),
    reference_available: node.reference_available as boolean | null ?? null, target: null }
}

export function parseMeaningPage(value: unknown): MeaningPage {
  const page = record(value)
  const senses: Meaning[] = list(page.senses).map(value => {
    const sense = record(value), learning = sense.learning == null ? null : record(sense.learning)
    if (!Number.isSafeInteger(sense.sense_id) || Number(sense.sense_id) < 1 || learning && !['DUE', 'NEW', 'NOT_YET_DUE'].includes(text(learning.state))) throw new HomeApiError(502, 'invalid_response')
    return { sense_id: Number(sense.sense_id), lemma: text(sense.lemma), pos: text(sense.pos), definition: nullable(sense.definition), cefr_level: nullable(sense.cefr_level),
      learning: learning ? { state: learning.state as LearningState, last_reviewed_at: learning.last_reviewed_at == null ? null : timestamp(learning.last_reviewed_at), due_at: learning.due_at == null ? null : timestamp(learning.due_at) } : null,
      examples: sense.examples == null ? [] : list(sense.examples).map(value => { const example = record(value); return { text: text(example.content) } }),
      sources: sense.sources == null ? [] : list(sense.sources).map(value => { const source = record(value); const space = text(source.space); if (space !== 'PERSONAL' && space !== 'PUBLISHED') throw new HomeApiError(502, 'invalid_response'); return { id: text(source.id), name: text(source.name), owner_id: text(source.owner_id), space } }),
      sources_has_more: sense.sources_has_more === true }
  })
  if (new Set(senses.map(sense => sense.sense_id)).size !== senses.length) throw new HomeApiError(502, 'invalid_response')
  return { senses, next_cursor: nullable(page.next_cursor) }
}
