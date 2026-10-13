import { queryOptions } from '@tanstack/react-query'
import type { FrontendServices } from '@/lib/api/services/contracts'

export function dictionaryState(params: Pick<URLSearchParams, 'get'>) {
  const raw = params.get('word'), id = raw ? Number(raw) : null
  return { query: params.get('q')?.trim() ?? '', wordId: id !== null && Number.isSafeInteger(id) && id > 0 ? id : null }
}
export function dictionaryQueries(services: FrontendServices, scope: string, query: string, wordId: number | null) {
  return {
    search: queryOptions({ queryKey: [services.mode, scope, 'dictionary-search', query], queryFn: ({ signal }) => services.dictionary.search(query, signal), enabled: Boolean(query) }),
    word: queryOptions({ queryKey: [services.mode, scope, 'dictionary-word', wordId], queryFn: ({ signal }) => services.dictionary.word(wordId!, signal), enabled: wordId !== null }),
    context: queryOptions({ queryKey: [services.mode, scope, 'dictionary-context', wordId], queryFn: ({ signal }) => services.dictionary.context(wordId!, signal), enabled: wordId !== null && scope !== 'signed-out' }),
  }
}
