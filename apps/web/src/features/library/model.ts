import type { LibraryNode } from '../../lib/api/study'
import { motifNames } from '@/components/artwork/artwork'

export type LearningState = 'new' | 'due' | 'not_yet_due'
export type MeaningFilter = 'all' | LearningState
export type MeaningSort = 'lemma_asc' | 'last_reviewed_desc'
export type LibraryTab = 'overview' | 'words'
export type LibraryTarget = { id: string; name: string; type: 'deck' | 'folder'; owner_id: string; space: LibraryDetails['space'] }
export type LibraryDetails = {
  id: string; name: string; type: LibraryNode['type']; description: string | null
  owner_id: string; space: 'personal' | 'published' | 'library'; role: string
  created_at: string; updated_at: string
  breadcrumbs: { id: string; name: string }[]
  reference_available: boolean | null; target: LibraryTarget | null
}
export type Meaning = {
  sense_id: number; lemma: string; pos: string; definition: string | null
  cefr_level: string | null; examples: { text: string }[]
  learning: { state: LearningState; last_reviewed_at: string | null; due_at: string | null } | null
  sources: { id: string; name: string; owner_id: string; space: 'personal' | 'published' }[]; sources_has_more: boolean
}
export type MeaningPage = { senses: Meaning[]; next_cursor: string | null }
export type SourcesPage = { decks: Meaning['sources']; next_cursor: string | null }
export type MeaningOptions = { q?: string; state?: MeaningFilter; sort?: MeaningSort; cursor?: string; limit?: number }
export type ContentsOptions = { q?: string; cursor?: string; limit?: number; includeProgress?: boolean }

export function libraryHref(nodeId?: string, tab?: LibraryTab): string {
  if (!nodeId) return '/app/personal'
  return `/app/personal/${encodeURIComponent(nodeId)}${tab === 'words' ? '/words' : ''}`
}

export function publicCollectionHref(identifier: string, nodeId?: string, tab?: LibraryTab): string {
  const base = `/u/${encodeURIComponent(identifier)}`
  return nodeId ? `${base}/${encodeURIComponent(nodeId)}${tab === 'words' ? '/words' : ''}` : base
}
export function publishedHref(nodeId?: string, tab?: LibraryTab): string {
  return nodeId ? `/app/published/${encodeURIComponent(nodeId)}${tab === 'words' ? '/words' : ''}` : '/app/published'
}
export function nodeHref(node: Pick<LibraryDetails, 'id' | 'owner_id' | 'space'>, tab?: LibraryTab, viewerId?: string): string {
  return node.space === 'published' ? node.owner_id === viewerId ? publishedHref(node.id, tab) : publicCollectionHref(node.owner_id, node.id, tab) : libraryHref(node.id, tab)
}

export function libraryMotif(id: string) {
  let seed = 2166136261
  for (const char of id) seed = Math.imul(seed ^ char.charCodeAt(0), 16777619)
  return motifNames[(seed >>> 0) % motifNames.length]
}

export function isDeck(node: LibraryDetails): boolean {
  return node.type === 'deck' || node.type === 'reference' && node.target?.type === 'deck'
}

export function libraryNodeKind(node: LibraryNode): 'deck' | 'folder' | null {
  return node.type === 'reference' ? node.target_type ?? null : node.type
}

export function libraryNodeLabel(node: LibraryNode): string {
  const kind = libraryNodeKind(node)
  return node.type === 'reference' ? kind === 'folder' ? 'Folder reference' : kind === 'deck' ? 'Deck reference' : 'Unavailable reference' : kind === 'folder' ? 'Folder' : 'Deck'
}

export function learningLabel(state: LearningState) {
  return state === 'due' ? 'Due' : state === 'new' ? 'New' : 'Not yet due'
}

export function dateLabel(value: string | null, timezone = 'UTC'): string {
  return value ? new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', timeZone: timezone }).format(new Date(value)) : '—'
}
