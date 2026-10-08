import type { LibraryNode, StudySummary } from './home-api'
import { motifNames } from '@/components/artwork/artwork'

export type LearningState = 'NEW' | 'DUE' | 'NOT_YET_DUE'
export type MeaningFilter = 'ALL' | LearningState
export type MeaningSort = 'LEMMA_ASC' | 'LAST_REVIEWED_DESC'
export type LibraryTab = 'overview' | 'words'
export type LibraryTarget = { id: string; name: string; type: 'DECK' | 'FOLDER'; owner_id: string; space: LibraryDetails['space'] }
export type LibraryDetails = {
  id: string; name: string; type: LibraryNode['type']; description: string | null
  owner_id: string; space: 'PERSONAL' | 'PUBLISHED' | 'LIBRARY'; role: string
  created_at: string; updated_at: string
  breadcrumbs: { id: string; name: string }[]
  summary: StudySummary | null
  reference_available: boolean | null; target: LibraryTarget | null
}
export type Meaning = {
  sense_id: number; lemma: string; pos: string; definition: string | null
  cefr_level: string | null; examples: { text: string }[]
  learning: { state: LearningState; last_reviewed_at: string | null; due_at: string | null } | null
  sources: { id: string; name: string; owner_id: string; space: 'PERSONAL' | 'PUBLISHED' }[]; sources_has_more: boolean
}
export type MeaningPage = { senses: Meaning[]; next_cursor: string | null }
export type SourcesPage = { decks: Meaning['sources']; next_cursor: string | null }
export type MeaningOptions = { q?: string; state?: MeaningFilter; sort?: MeaningSort; cursor?: string; limit?: number }
export type ContentsOptions = { q?: string; cursor?: string; limit?: number }

export function libraryHref(nodeId?: string, tab?: LibraryTab): string {
  if (!nodeId) return '/app/personal'
  return `/app/personal/${encodeURIComponent(nodeId)}${tab === 'words' ? '/words' : ''}`
}

export function publishedHref(ownerId: string, nodeId?: string, tab?: LibraryTab): string {
  const base = `/app/u/${encodeURIComponent(ownerId)}/published`
  return nodeId ? `${base}/${encodeURIComponent(nodeId)}${tab === 'words' ? '/words' : ''}` : base
}

export function nodeHref(node: Pick<LibraryDetails, 'id' | 'owner_id' | 'space'>, tab?: LibraryTab): string {
  return node.space === 'PUBLISHED' ? publishedHref(node.owner_id, node.id, tab) : libraryHref(node.id, tab)
}

export function libraryMotif(id: string) {
  let seed = 2166136261
  for (const char of id) seed = Math.imul(seed ^ char.charCodeAt(0), 16777619)
  return motifNames[(seed >>> 0) % motifNames.length]
}

export function isDeck(node: LibraryDetails): boolean {
  return node.type === 'DECK' || node.type === 'REFERENCE' && node.target?.type === 'DECK'
}

export function libraryNodeKind(node: LibraryNode): 'DECK' | 'FOLDER' | null {
  return node.type === 'REFERENCE' ? node.target_type ?? null : node.type
}

export function libraryNodeLabel(node: LibraryNode): string {
  const kind = libraryNodeKind(node)
  return node.type === 'REFERENCE' ? kind === 'FOLDER' ? 'Folder reference' : kind === 'DECK' ? 'Deck reference' : 'Unavailable reference' : kind === 'FOLDER' ? 'Folder' : 'Deck'
}

export function learningLabel(state: LearningState) {
  return state === 'DUE' ? 'Due' : state === 'NEW' ? 'New' : 'Not yet due'
}

export function dateLabel(value: string | null, timezone = 'UTC'): string {
  return value ? new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', timeZone: timezone }).format(new Date(value)) : '—'
}
