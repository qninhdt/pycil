'use client'

import { useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQueryClient } from '@tanstack/react-query'
import { Icon } from '@/components/artwork/artwork'
import type { AccountProfile } from '@/lib/api'
import { libraryHref, publishedHref } from '@/lib/library-model'
import { useServices } from '@/lib/services/provider'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { LibraryDestinationDialog, type Destination } from './library-destination-dialog'

type Props = {
  profile: AccountProfile; kind: 'FOLDER' | 'DECK'; open: boolean; onOpenChange: (open: boolean) => void
  parent?: { id: string; name: string; space: 'PERSONAL' | 'PUBLISHED' }
  destinationEnabled?: boolean
  editing?: { id: string; name: string; description: string | null }
  onCreated?: (id: string) => void
}

export function LibraryNodeForm({ profile, kind, open, onOpenChange, parent, destinationEnabled = false, editing, onCreated }: Props) {
  const router = useRouter(), queryClient = useQueryClient(), { services } = useServices()
  const [name, setName] = useState(editing?.name ?? '')
  const [description, setDescription] = useState(editing?.description ?? '')
  const [destination, setDestination] = useState<Destination>(parent ? { ...parent, type: 'FOLDER' } : { id: profile.personal_node_id, name: 'Personal', type: 'FOLDER', space: 'PERSONAL' })
  const [picking, setPicking] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const submitting = useRef(false)
  const label = kind === 'DECK' ? 'deck' : 'folder'
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!name.trim() || submitting.current || (!editing && destination.space === 'PUBLISHED' && !confirmed)) return
    submitting.current = true
    setBusy(true); setError('')
    try {
      if (editing) {
        await services.library.updateNode(editing.id, { name: name.trim(), description: description.trim() || null }, new AbortController().signal)
        await queryClient.invalidateQueries({ queryKey: [services.mode] })
        onOpenChange(false)
      }
      else {
        const id = await services.library.createNode({ parentId: destination.id, type: kind, name: name.trim(), description: description.trim() || null, confirmPublication: confirmed }, new AbortController().signal)
        await queryClient.invalidateQueries({ queryKey: [services.mode] })
        if (onCreated) onCreated(id)
        else router.push(destination.space === 'PUBLISHED' ? publishedHref(profile.id, id) : libraryHref(id))
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : `Could not save this ${label}. Please retry.`) }
    finally { submitting.current = false; setBusy(false) }
  }
  return <>
    <Dialog open={open && !picking} onOpenChange={onOpenChange}><DialogContent className="w-[min(calc(100%-2rem),480px)] max-w-[480px]">
      <DialogHeader><DialogTitle>{editing ? `Edit ${label}` : `New ${label}`}</DialogTitle><DialogDescription>{editing ? 'Update the title and description.' : `Add a ${label} to your Library.`}</DialogDescription></DialogHeader>
      <form className="grid gap-2 [&_label]:text-xs [&_label]:font-bold [&_label]:mt-2 [&_label_span]:font-normal [&_label_span]:text-muted-foreground" onSubmit={event => { void submit(event) }}>
        <label htmlFor="library-node-name">Title</label><Input id="library-node-name" value={name} onChange={event => setName(event.target.value)} maxLength={255} required autoFocus placeholder={kind === 'DECK' ? 'e.g. Everyday English' : 'e.g. Language study'} />
        <label htmlFor="library-node-description">Description <span>(optional)</span></label><Textarea id="library-node-description" value={description} onChange={event => setDescription(event.target.value)} maxLength={8000} rows={3} placeholder="What belongs here?" />
        {!editing && <><label>Destination</label>{destinationEnabled
          ? <button type="button" className="library-destination-field hover:bg-accent flex items-center gap-2.5 min-h-[42px] px-3 py-2 border border-border text-left [&_>_svg]:size-[18px] [&_>_span:last-child:not(:first-of-type)]:ml-auto [&_>_span:last-child:not(:first-of-type)]:text-xs [&_>_span:last-child:not(:first-of-type)]:underline" onClick={() => setPicking(true)}><Icon name="folder" /><span>{destination.name}</span><span>Change</span></button>
          : <div className="library-destination-field flex items-center gap-2.5 min-h-[42px] px-3 py-2 border border-border text-left [&_>_svg]:size-[18px] [&_>_span:last-child:not(:first-of-type)]:ml-auto [&_>_span:last-child:not(:first-of-type)]:text-xs [&_>_span:last-child:not(:first-of-type)]:underline" aria-label={`Destination: ${destination.name}`}><Icon name="folder" /><span>{destination.name}</span></div>}</>}
        {!editing && destination.space === 'PUBLISHED' && <label className="flex items-start gap-2"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />Make this {label} publicly readable.</label>}
        {error && <p className="text-destructive text-xs" role="alert">{error}</p>}
        <div className="flex justify-end gap-2 mt-4"><Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button><Button type="submit" disabled={busy || !name.trim() || (!editing && destination.space === 'PUBLISHED' && !confirmed)}>{busy ? 'Saving…' : editing ? 'Save changes' : `Create ${label}`}</Button></div>
      </form>
    </DialogContent></Dialog>
    {picking && <LibraryDestinationDialog open onOpenChange={next => { if (!next) setPicking(false) }} profile={profile} kind="FOLDER" action="Use this folder"
      onConfirm={async selected => { const detail = await services.library.details(selected.id, new AbortController().signal); setDestination({ ...selected, space: detail.space === 'PUBLISHED' ? 'PUBLISHED' : 'PERSONAL' }); setConfirmed(false); setPicking(false) }} />}
  </>
}
