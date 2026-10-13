import 'server-only'

import { dehydrate, type QueryClient } from '@tanstack/react-query'
import { dataMode } from '@/lib/api/services/config'

export function dehydrateRoute(client: QueryClient) {
  const state = dehydrate(client)
  if (dataMode === 'mock') for (const query of state.queries) query.state.dataUpdatedAt = 0
  return state
}
