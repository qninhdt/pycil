import { queryOptions } from '@tanstack/react-query'
import type { FrontendServices } from '@/lib/api/services/contracts'
import type { ContentsOptions, MeaningOptions } from '@/features/library/model'

export function contentsOptions(params: Pick<URLSearchParams, 'get' | 'getAll'>): ContentsOptions {
  return { q: params.get('q')?.trim() ?? '', cursor: params.getAll('cursor').at(-1), limit: 12 }
}
export function meaningOptions(params: Pick<URLSearchParams, 'get' | 'getAll'>): MeaningOptions {
  const state = params.get('state'), sort = params.get('sort')
  return { ...contentsOptions(params), state: state === 'new' || state === 'due' || state === 'not_yet_due' ? state : 'all',
    sort: sort === 'last_reviewed_desc' ? sort : 'lemma_asc' }
}
export function nodeQuery(services: FrontendServices, scope: string, id: string) {
  return queryOptions({ queryKey: [services.mode, scope, 'library-node', id],
    queryFn: ({ signal }) => scope === 'signed-out' ? services.library.publicNode(id, signal) : services.library.metadata(id, signal), enabled: Boolean(id) })
}
export function contentsQuery(services: FrontendServices, scope: string, id: string, options: ContentsOptions) {
  const publicRead = scope === 'signed-out'
  return queryOptions({ queryKey: [services.mode, scope, 'library-contents', id, options, publicRead], queryFn: ({ signal }) => services.library.contents(id, options, signal, publicRead) })
}
export function meaningsQuery(services: FrontendServices, scope: string, id: string, options: MeaningOptions) {
  return queryOptions({ queryKey: [services.mode, scope, 'library-meanings', id, options], queryFn: ({ signal }) => services.library.meanings(id, options, signal) })
}

export function progressQuery(services: FrontendServices, scope: string, id: string) {
  return queryOptions({ queryKey: [services.mode, scope, 'node-progress', id],
    queryFn: ({ signal }) => services.learning.summary(id, signal), enabled: Boolean(id) && scope !== 'signed-out' })
}
