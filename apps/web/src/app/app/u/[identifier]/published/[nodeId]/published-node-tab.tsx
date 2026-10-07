'use client'

import { useSelectedLayoutSegment } from 'next/navigation'
import { PublishedRoute } from '@/components/library/published-route'

export function PublishedNodeTab({ identifier, nodeId }: { identifier: string; nodeId: string }) {
  const segment = useSelectedLayoutSegment()
  return <PublishedRoute identifier={identifier} nodeId={nodeId} tab={segment === 'words' ? 'words' : 'overview'} />
}
