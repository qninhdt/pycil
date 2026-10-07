'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import { Copy, MoreHorizontal, MoveRight, Trash2 } from '@/components/artwork/artwork'
import { Icon } from '@/components/artwork/artwork'
import { toast } from 'sonner'
import { useAccount } from '@/components/application/providers'
import { useServices } from '@/lib/services/provider'
import { libraryHref, publishedHref } from '@/lib/library-model'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { LibraryDestinationDialog } from './library-destination-dialog'
import { LibraryNodeForm } from './library-node-form'

type Node = { id: string; name: string; description: string | null; type: 'FOLDER' | 'DECK' | 'REFERENCE'; owner_id?: string }

export function LibraryNodeActions({ node, space, parentId, onDeleted, onCopyLink, allowEdit = true, className }: { node: Node; space: 'PERSONAL' | 'PUBLISHED'; parentId?: string; onDeleted?: () => void; onCopyLink?: () => void; allowEdit?: boolean; className?: string }) {
  const account = useAccount(), { services } = useServices(), queryClient = useQueryClient(), router = useRouter()
  const [action, setAction] = useState<'edit' | 'move' | 'copy' | 'delete' | null>(null)
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const profile = account.profile
  const canEdit = allowEdit && !!profile && node.owner_id === profile.id
  if (!canEdit && !onCopyLink) return null
  const kind = node.type === 'DECK' ? 'DECK' : 'FOLDER'
  async function destination(id: string) {
    setBusy(true); setError('')
    try {
      if (action === 'move') await services.library.moveNode(node.id, id, new AbortController().signal)
      else await services.library.copyNode(node.id, id, new AbortController().signal)
      await queryClient.invalidateQueries({ queryKey: [services.mode] })
      toast.success(action === 'move' ? 'Moved' : 'Copied')
      setAction(null)
      if (action === 'move' && !parentId) router.push(space === 'PUBLISHED' ? publishedHref(profile!.id, id) : libraryHref(id))
    } catch (cause) { const message = cause instanceof Error ? cause.message : 'Could not complete this action.'; setError(message); throw cause }
    finally { setBusy(false) }
  }
  async function remove() {
    setBusy(true); setError('')
    try {
      await services.library.deleteNode(node.id, new AbortController().signal)
      await queryClient.invalidateQueries({ queryKey: [services.mode] })
      setAction(null); toast.success(`${kind === 'DECK' ? 'Deck' : 'Folder'} deleted`)
      if (onDeleted) onDeleted()
      else if (parentId) router.refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not delete this item.') }
    finally { setBusy(false) }
  }
  return <>
    <DropdownMenu><DropdownMenuTrigger asChild><Button type="button" variant="ghost" size="icon-sm" className={className ?? "absolute top-2 right-2 z-[2] group-data-[view=list]:top-1/2 group-data-[view=list]:-translate-y-1/2"} aria-label={`${onCopyLink ? 'Settings' : 'Actions'} for ${node.name}`}><MoreHorizontal aria-hidden="true" /></Button></DropdownMenuTrigger>
      <DropdownMenuContent align="end">{onCopyLink && <DropdownMenuItem onSelect={onCopyLink}><Copy aria-hidden="true" />Copy link</DropdownMenuItem>}
        {canEdit && <>{onCopyLink && <DropdownMenuSeparator />}<DropdownMenuItem onSelect={() => { setError(''); setAction('edit') }}><Icon name="edit" className="size-4" />Edit details</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => { setError(''); setAction('move') }}><MoveRight aria-hidden="true" />Move</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => { setError(''); setAction('copy') }}><Copy aria-hidden="true" />Copy</DropdownMenuItem>
        <DropdownMenuSeparator /><DropdownMenuItem variant="destructive" onSelect={() => { setError(''); setAction('delete') }}><Trash2 aria-hidden="true" />Delete</DropdownMenuItem></>}
      </DropdownMenuContent></DropdownMenu>
    {action === 'edit' && profile && <LibraryNodeForm key={node.id} profile={profile} kind={kind} open onOpenChange={open => { if (!open) setAction(null) }} editing={node} />}
    {(action === 'move' || action === 'copy') && profile && <LibraryDestinationDialog open onOpenChange={open => { if (!open) setAction(null) }} profile={profile} kind="FOLDER" action={action === 'move' ? 'Move here' : 'Copy here'}
      spaceOnly={space === 'PUBLISHED' ? 'published' : 'personal'} excludedIds={new Set([node.id, ...(action === 'move' && parentId ? [parentId] : [])])} onConfirm={selected => destination(selected.id)} />}
    <AlertDialog open={action === 'delete'} onOpenChange={open => { if (!open) setAction(null) }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Delete “{node.name}”?</AlertDialogTitle>
      <AlertDialogDescription>{kind === 'FOLDER' ? 'This also deletes everything inside this folder.' : 'This deck and its saved meanings will be removed from your Library.'}</AlertDialogDescription></AlertDialogHeader>
      {error && <p className="text-destructive text-xs" role="alert">{error}</p>}
      <AlertDialogFooter><AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={busy} onClick={event => { event.preventDefault(); void remove() }}>{busy ? 'Deleting…' : 'Delete'}</AlertDialogAction></AlertDialogFooter>
    </AlertDialogContent></AlertDialog>
  </>
}
