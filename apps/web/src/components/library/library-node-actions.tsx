'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import { ArrowUpLeft, Copy, MoreHorizontal, MoveRight, Pencil, Share2, Trash2 } from '@/components/artwork/artwork'
import { toast } from 'sonner'
import { useAccount } from '@/components/application/providers'
import { useServices } from '@/lib/services/provider'
import { libraryHref, publishedHref } from '@/lib/library-model'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { LibraryDestinationDialog } from './library-destination-dialog'
import { LibraryNodeForm } from './library-node-form'

type Node = { id: string; name: string; description: string | null; type: 'FOLDER' | 'DECK' | 'REFERENCE'; owner_id?: string; reference_id?: string | null; target?: { id: string } | null }

export function LibraryNodeActions({ node, space, parentId, onDeleted, onCopyLink, allowEdit = true, className }: { node: Node; space: 'PERSONAL' | 'PUBLISHED'; parentId?: string; onDeleted?: () => void; onCopyLink?: () => void; allowEdit?: boolean; className?: string }) {
  const t = useTranslations('library')
  const tCommon = useTranslations('common')
  const account = useAccount(), { services } = useServices(), queryClient = useQueryClient(), router = useRouter()
  const [action, setAction] = useState<'edit' | 'move' | 'copy' | 'reference' | 'delete' | 'publish' | 'unpublish' | null>(null)
  const [retainReference, setRetainReference] = useState(false)
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const profile = account.profile
  const canEdit = allowEdit && !!profile && node.owner_id === profile.id
  const referenceId = node.type === 'REFERENCE' ? space === 'PUBLISHED' ? node.reference_id ?? node.target?.id : null : node.id
  const canReference = !!profile && !!referenceId && (canEdit || space === 'PUBLISHED')
  if (!canEdit && !onCopyLink && !canReference) return null
  const kind = node.type === 'DECK' ? 'DECK' : 'FOLDER'
  async function destination(id: string) {
    setBusy(true); setError('')
    try {
      if (action === 'move') await services.library.moveNode(node.id, id, new AbortController().signal)
      else await services.library.copyNode(node.id, id, new AbortController().signal, space === 'PUBLISHED')
      await queryClient.invalidateQueries({ queryKey: [services.mode] })
      toast.success(action === 'move' ? t('moved') : t('copied'))
      setAction(null)
      if (action === 'move' && !parentId) router.push(space === 'PUBLISHED' ? publishedHref(profile!.id, id) : libraryHref(id))
    } catch (cause) { const message = cause instanceof Error ? cause.message : t('couldNotCompleteAction'); setError(message); throw cause }
    finally { setBusy(false) }
  }
  async function remove() {
    setBusy(true); setError('')
    try {
      await services.library.deleteNode(node.id, new AbortController().signal)
      await queryClient.invalidateQueries({ queryKey: [services.mode] })
      setAction(null); toast.success(kind === 'DECK' ? t('deckDeleted') : t('folderDeleted'))
      if (onDeleted) onDeleted()
      else if (parentId) router.refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : t('couldNotDeleteItem')) }
    finally { setBusy(false) }
  }
  async function changePublication() {
    if (!profile || busy) return
    setBusy(true); setError('')
    const publishing = action === 'publish'
    try {
      await services.library.moveNode(node.id, publishing ? profile.published_node_id : profile.personal_node_id, new AbortController().signal, { confirm: publishing, retainReference: publishing && retainReference })
      await queryClient.invalidateQueries({ queryKey: [services.mode] })
      setAction(null)
      router.push(publishing ? publishedHref(profile.id, node.id) : libraryHref(node.id))
      toast.success(publishing ? t('published') : t('movedToPersonal'))
    } catch (cause) { setError(cause instanceof Error ? cause.message : t('couldNotChangePublication')) }
    finally { setBusy(false) }
  }
  return <>
    <DropdownMenu><DropdownMenuTrigger asChild><Button type="button" variant="ghost" size="icon-sm" className={className ?? "absolute top-2 right-2 z-[2] group-data-[view=list]:top-1/2 group-data-[view=list]:-translate-y-1/2"} aria-label={onCopyLink ? t('settingsFor', { name: node.name }) : t('actionsFor', { name: node.name })}><MoreHorizontal aria-hidden="true" /></Button></DropdownMenuTrigger>
      <DropdownMenuContent align="end">{onCopyLink && <DropdownMenuItem onSelect={onCopyLink}><Copy aria-hidden="true" />{t('copyLink')}</DropdownMenuItem>}
        {canEdit && <>{onCopyLink && <DropdownMenuSeparator />}<DropdownMenuItem onSelect={() => { setError(''); setAction('edit') }}><Pencil aria-hidden="true" />{t('editDetails')}</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => { setError(''); setAction('move') }}><MoveRight aria-hidden="true" />{t('move')}</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => { setError(''); setAction('copy') }}><Copy aria-hidden="true" />{t('copy')}</DropdownMenuItem></>}
        {canReference && <DropdownMenuItem onSelect={() => { setError(''); setAction('reference') }}><ArrowUpLeft aria-hidden="true" />{t('createReference')}</DropdownMenuItem>}
        {canEdit && <><DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => { setError(''); setRetainReference(false); setAction(space === 'PUBLISHED' ? 'unpublish' : 'publish') }}><Share2 aria-hidden="true" />{space === 'PUBLISHED' ? t('moveToPersonal') : t('publish')}</DropdownMenuItem>
        <DropdownMenuSeparator /><DropdownMenuItem variant="destructive" onSelect={() => { setError(''); setAction('delete') }}><Trash2 aria-hidden="true" />{tCommon('delete')}</DropdownMenuItem></>}
      </DropdownMenuContent></DropdownMenu>
    {action === 'edit' && profile && <LibraryNodeForm key={node.id} profile={profile} kind={kind} open onOpenChange={open => { if (!open) setAction(null) }} editing={node} />}
    {action === 'reference' && profile && referenceId && <LibraryNodeForm profile={profile} kind={kind} open destinationEnabled
      referenceTarget={{ id: referenceId, name: node.name, space }} onOpenChange={open => { if (!open) setAction(null) }}
      onCreated={() => { setAction(null); toast.success(t('referenceCreated')) }} />}
    {(action === 'move' || action === 'copy') && profile && <LibraryDestinationDialog open onOpenChange={open => { if (!open) setAction(null) }} profile={profile} kind="FOLDER" action={action === 'move' ? t('moveHere') : t('copyHere')}
      spaceOnly={space === 'PUBLISHED' ? 'published' : 'personal'} requirePublicationConfirmation={action === 'copy' && space === 'PUBLISHED'} excludedIds={new Set([node.id, ...(action === 'move' && parentId ? [parentId] : [])])} onConfirm={selected => destination(selected.id)} />}
    <AlertDialog open={action === 'publish' || action === 'unpublish'} onOpenChange={open => { if (!open && !busy) setAction(null) }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{action === 'publish' ? t('publishPromptTitle', { name: node.name }) : t('unpublishPromptTitle', { name: node.name })}</AlertDialogTitle><AlertDialogDescription>{action === 'publish' ? t('publishPromptDesc') : t('unpublishPromptDesc')}</AlertDialogDescription></AlertDialogHeader>
      {action === 'publish' && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={retainReference} onChange={event => setRetainReference(event.target.checked)} />{t('keepReferenceInPersonal')}</label>}
      {error && <p role="alert" className="text-destructive text-xs">{error}</p>}
      <AlertDialogFooter><AlertDialogCancel disabled={busy}>{tCommon('cancel')}</AlertDialogCancel><AlertDialogAction disabled={busy} onClick={event => { event.preventDefault(); void changePublication() }}>{busy ? tCommon('saving') : action === 'publish' ? t('publish') : t('moveToPersonal')}</AlertDialogAction></AlertDialogFooter>
    </AlertDialogContent></AlertDialog>
    <AlertDialog open={action === 'delete'} onOpenChange={open => { if (!open) setAction(null) }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{t('deletePromptTitle', { name: node.name })}</AlertDialogTitle>
      <AlertDialogDescription>{kind === 'FOLDER' ? t('deleteFolderDesc') : t('deleteDeckDesc')}</AlertDialogDescription></AlertDialogHeader>
      {error && <p className="text-destructive text-xs" role="alert">{error}</p>}
      <AlertDialogFooter><AlertDialogCancel disabled={busy}>{tCommon('cancel')}</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={busy} onClick={event => { event.preventDefault(); void remove() }}>{busy ? tCommon('deleting') : tCommon('delete')}</AlertDialogAction></AlertDialogFooter>
    </AlertDialogContent></AlertDialog>
  </>
}
