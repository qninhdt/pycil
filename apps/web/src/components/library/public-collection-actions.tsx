'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { useAccount } from '@/components/application/providers'
import { Button } from '@/components/ui/button'
import { useServices } from '@/lib/services/provider'
import { HomeFailure } from '@/components/home/home-state'
import { publishedHref } from '@/lib/library-model'
import { LibraryDestinationDialog } from './library-destination-dialog'
import { LibraryStudy } from './library-study'

export function PublicCollectionActions({ nodeId, name, targetId, ownerId }: { nodeId: string; name: string; targetId?: string; ownerId: string }) {
  const account = useAccount(), { services, scope } = useServices(), queryClient = useQueryClient()
  const [picking, setPicking] = useState(false)
  const details = useQuery({ queryKey: [services.mode, scope, 'library-node', nodeId], queryFn: ({ signal }) => services.library.details(nodeId, signal), enabled: account.status === 'ready' })
  if (account.status !== 'ready' || !account.profile) return <Button asChild variant="outline" className="mt-4"><Link href={`/login?returnTo=${encodeURIComponent(publishedHref(ownerId, nodeId))}`}>Sign in to save or study</Link></Button>
  return <div className="mt-4">
    <Button variant="outline" onClick={() => setPicking(true)}>Save to Personal</Button>
    {details.isError ? <HomeFailure label="study actions" error={details.error} retry={() => { void details.refetch() }} /> : details.data?.summary && <LibraryStudy summary={details.data.summary} nodeId={nodeId} publishedOwner={ownerId} />}
    {picking && <LibraryDestinationDialog open profile={account.profile} kind="FOLDER" spaceOnly="personal" action="Save reference" onOpenChange={setPicking} onConfirm={async destination => {
      await services.library.createReference(destination.id, targetId ?? nodeId, name, new AbortController().signal)
      await queryClient.invalidateQueries({ queryKey: [services.mode] })
      toast.success('Reference saved to Personal')
    }} />}
  </div>
}
