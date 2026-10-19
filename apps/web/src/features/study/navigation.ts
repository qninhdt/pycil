import type { AccountProfile } from '@/lib/api/account'
import { libraryHref, publishedHref, publicCollectionHref } from '@/features/library/model'

export function studyReturnHref(nodeId: string, profile: AccountProfile | null, owner?: string | null): string {
  if (!nodeId || nodeId === profile?.library_node_id) return '/app'
  if (nodeId === profile?.personal_node_id) return libraryHref()
  if (nodeId === profile?.published_node_id) return publishedHref()
  if (owner) return owner === profile?.id ? publishedHref(nodeId) : publicCollectionHref(owner, nodeId)
  return libraryHref(nodeId)
}
