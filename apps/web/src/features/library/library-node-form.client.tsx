'use client'

import { useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import { Icon } from '@/components/artwork/artwork'
import type { AccountProfile } from '@/lib/api/account'
import { libraryHref, publishedHref } from '@/features/library/model'
import { invalidateLibrary } from '@/features/library/invalidate'
import { useServices } from '@/lib/api/services/provider.client'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { LibraryDestinationDialog, type Destination } from './library-destination-dialog.client'

type Props = {
  profile: AccountProfile; kind: 'folder' | 'deck'; open: boolean; onOpenChange: (open: boolean) => void
  parent?: { id: string; name: string; space: 'personal' | 'published' }
  destinationEnabled?: boolean
  editing?: { id: string; name: string; description: string | null }
  referenceTarget?: { id: string; name: string; space: 'personal' | 'published' }
  onCreated?: (id: string) => void
}

export function LibraryNodeForm({ profile, kind, open, onOpenChange, parent, destinationEnabled = false, editing, referenceTarget, onCreated }: Props) {
  const t = useTranslations('library')
  const tCommon = useTranslations('common')
  const router = useRouter(), queryClient = useQueryClient(), { services, scope } = useServices()
  const [name, setName] = useState(editing?.name ?? referenceTarget?.name ?? '')
  const [description, setDescription] = useState(editing?.description ?? '')
  const [destination, setDestination] = useState<Destination>(parent ? { ...parent, type: 'folder' } : { id: profile.personal_node_id, name: t('personal'), type: 'folder', space: 'personal' })
  const [picking, setPicking] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const submitting = useRef(false)
  const label = referenceTarget ? t('reference') : kind === 'deck' ? t('kindDeck') : t('kindFolder')
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!name.trim() || submitting.current || (!editing && destination.space === 'published' && !confirmed)) return
    submitting.current = true
    setBusy(true); setError('')
    try {
      if (editing) {
        await services.library.updateNode(editing.id, { name: name.trim(), description: description.trim() || null }, new AbortController().signal)
        await invalidateLibrary(queryClient, services.mode, scope)
        onOpenChange(false)
      }
      else {
        const id = referenceTarget
          ? await services.library.createReference(destination.id, referenceTarget.id, name.trim(), new AbortController().signal, confirmed)
          : await services.library.createNode({ parentId: destination.id, type: kind, name: name.trim(), description: description.trim() || null, confirmPublication: confirmed }, new AbortController().signal)
        await invalidateLibrary(queryClient, services.mode, scope)
        if (onCreated) onCreated(id)
        else router.push(destination.space === 'published' ? publishedHref(id) : libraryHref(id))
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : t('couldNotSaveNode', { kind: label })) }
    finally { submitting.current = false; setBusy(false) }
  }
  return <>
    <Dialog open={open && !picking} onOpenChange={onOpenChange}><DialogContent className="w-[min(calc(100%-2rem),480px)] max-w-[480px]">
      <DialogHeader><DialogTitle>{editing ? t('editNodeTitle', { kind: label }) : referenceTarget ? t('createReference') : t('newNodeTitle', { kind: label })}</DialogTitle><DialogDescription>{editing ? t('editNodeDesc') : referenceTarget ? t('referenceDesc', { name: referenceTarget.name }) : t('newNodeDesc', { kind: label })}</DialogDescription></DialogHeader>
      <form className="grid gap-2 [&_label]:text-xs [&_label]:font-bold [&_label]:mt-2 [&_label_span]:font-normal [&_label_span]:text-muted-foreground" onSubmit={event => { void submit(event) }}>
        <label htmlFor="library-node-name">{t('title')}</label><Input id="library-node-name" value={name} onChange={event => setName(event.target.value)} maxLength={255} required autoFocus placeholder={kind === 'deck' ? t('placeholderDeckTitle') : t('placeholderFolderTitle')} />
        {!referenceTarget && <><label htmlFor="library-node-description">{t('description')} <span>({t('optional')})</span></label><Textarea id="library-node-description" value={description} onChange={event => setDescription(event.target.value)} maxLength={8000} rows={3} placeholder={t('placeholderDesc')} /></>}
        {!editing && <><label>{t('destination')}</label>{destinationEnabled
          ? <button type="button" className="library-destination-field hover:bg-accent flex items-center gap-2.5 min-h-[42px] px-3 py-2 border border-border text-left [&_>_svg]:size-[18px] [&_>_span:last-child:not(:first-of-type)]:ml-auto [&_>_span:last-child:not(:first-of-type)]:text-xs [&_>_span:last-child:not(:first-of-type)]:underline" onClick={() => setPicking(true)}><Icon name="folder" /><span>{destination.name}</span><span>{t('change')}</span></button>
          : <div className="library-destination-field flex items-center gap-2.5 min-h-[42px] px-3 py-2 border border-border text-left [&_>_svg]:size-[18px] [&_>_span:last-child:not(:first-of-type)]:ml-auto [&_>_span:last-child:not(:first-of-type)]:text-xs [&_>_span:last-child:not(:first-of-type)]:underline" aria-label={`${t('destination')}: ${destination.name}`}><Icon name="folder" /><span>{destination.name}</span></div>}</>}
        {!editing && destination.space === 'published' && <label className="flex items-start gap-2"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />{t('makePubliclyReadable', { kind: label })}</label>}
        {error && <p className="text-destructive text-xs" role="alert">{error}</p>}
        <div className="flex justify-end gap-2 mt-4"><Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>{tCommon('cancel')}</Button><Button type="submit" disabled={busy || !name.trim() || (!editing && destination.space === 'published' && !confirmed)}>{busy ? tCommon('saving') : editing ? tCommon('saveChanges') : referenceTarget ? t('createReference') : t('createNodeButton', { kind: label })}</Button></div>
      </form>
    </DialogContent></Dialog>
    {picking && <LibraryDestinationDialog open onOpenChange={next => { if (!next) setPicking(false) }} profile={profile} kind="folder" action={t('useThisFolder')}
      spaceOnly={referenceTarget?.space === 'personal' ? 'personal' : undefined} excludedIds={referenceTarget ? new Set([referenceTarget.id]) : undefined}
      onConfirm={async selected => { const detail = await services.library.metadata(selected.id, new AbortController().signal); setDestination({ ...selected, space: detail.space === 'published' ? 'published' : 'personal' }); setConfirmed(false); setPicking(false) }} />}
  </>
}
