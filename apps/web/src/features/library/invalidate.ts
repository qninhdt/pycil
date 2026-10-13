import type { QueryClient } from '@tanstack/react-query'
import type { FrontendServices } from '@/lib/api/services/contracts'

const resources = new Set([
  'library-node', 'library-contents', 'library-meanings', 'library-preview', 'destination',
  'node-progress', 'progress', 'schedule', 'dictionary-context', 'discovery', 'flashcards',
  'public-node', 'public-contents', 'public-meanings',
])

export function invalidateLibrary(client: QueryClient, mode: FrontendServices['mode'], scope: string) {
  return client.invalidateQueries({ predicate: query =>
    query.queryKey[0] === mode && query.queryKey[1] === scope && resources.has(String(query.queryKey[2])) })
}
