'use client'

import { useDeferredValue, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, ChevronRight, Search } from '@/components/artwork/artwork'
import { Icon } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { useServices } from '@/lib/services/provider'
import type { AccountProfile } from '@/lib/api'

export type Destination = { id: string; name: string; type: 'DECK' | 'FOLDER'; space?: 'PERSONAL' | 'PUBLISHED' }
type Props = {
  open: boolean; onOpenChange: (open: boolean) => void; profile: AccountProfile
  kind: 'DECK' | 'FOLDER'; action: string; onConfirm: (destination: Destination) => Promise<void>
  excludedIds?: ReadonlySet<string>; onCreateDeck?: (parentId: string, name: string) => Promise<void>
  spaceOnly?: 'personal' | 'published'
}

export function LibraryDestinationDialog(props: Props) {
  const { open, onOpenChange, profile, kind, action, onConfirm, excludedIds, onCreateDeck, spaceOnly } = props
  const { services, scope } = useServices()
  const root = spaceOnly === 'personal' ? profile.personal_node_id : spaceOnly === 'published' ? profile.published_node_id : profile.library_node_id
  const [path, setPath] = useState<Destination[]>([])
  const current = path.at(-1) ?? { id: root, name: spaceOnly === 'personal' ? 'Personal' : spaceOnly === 'published' ? 'Published' : 'My Library', type: 'FOLDER' as const }
  const [search, setSearch] = useState(''), q = useDeferredValue(search)
  const [cursors, setCursors] = useState<string[]>([])
  const [selected, setSelected] = useState<Destination | null>(null)
  const [creating, setCreating] = useState(false), [newName, setNewName] = useState('')
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const query = useQuery({ queryKey: [services.mode, scope, 'destination', current.id, q, cursors.at(-1)],
    queryFn: ({ signal }) => services.library.contents(current.id, { q, cursor: cursors.at(-1), limit: 20 }, signal), enabled: open })
  async function navigate(item: Destination) {
    setBusy(true); setError('')
    try {
      const detail = await services.library.details(item.id, new AbortController().signal)
      const rootIndex = detail.breadcrumbs.findIndex(parent => parent.id === root)
      const parents = rootIndex < 0 ? path : detail.breadcrumbs.slice(rootIndex + 1).map(parent => ({ ...parent, type: 'FOLDER' as const }))
      setPath([...parents, item]); setSearch(''); setCursors([]); setSelected(null); setCreating(false)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not open this folder. Please retry.') }
    finally { setBusy(false) }
  }
  async function confirm() {
    const target = selected ?? (canSelectCurrent ? current : null)
    if (!target) return
    setBusy(true); setError('')
    try { await onConfirm(target); onOpenChange(false) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save this selection. Please retry.') }
    finally { setBusy(false) }
  }
  async function create() {
    if (!onCreateDeck || !newName.trim()) return
    setBusy(true); setError('')
    try { await onCreateDeck(current.id, newName.trim()); onOpenChange(false) }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not create this deck. Please retry.') }
    finally { setBusy(false) }
  }
  const items = query.data?.nodes.filter(node => node.type === 'FOLDER' || node.type === 'DECK') ?? []
  const canSelectCurrent = kind === 'FOLDER' && current.id !== profile.library_node_id && !excludedIds?.has(current.id)
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="destination-dialog w-[min(560px,calc(100vw-24px))] max-w-none sm:max-w-none max-h-[min(90vh,740px)] flex flex-col gap-0 p-0 bg-background" aria-describedby="destination-description">
    <DialogHeader className="p-0 text-left border-b border-border px-6 pt-[22px] pb-4"><DialogTitle className="text-2xl font-extrabold tracking-[-.03em]">Choose a destination</DialogTitle><DialogDescription id="destination-description" className="text-xs text-muted-foreground mt-1">{kind === 'DECK' ? 'Select a deck for this meaning.' : 'Select a folder.'}</DialogDescription></DialogHeader>
    <div className="destination-search flex items-center gap-2 border border-border mx-6 mt-4 px-2.5"><Search className="size-[17px] shrink-0 text-muted-foreground" aria-hidden="true" /><Input className="border-0 h-9" aria-label="Search folders and decks" placeholder="Search folders and decks" value={search} maxLength={200} onChange={event => { setSearch(event.target.value); setCursors([]); setSelected(null) }} /></div>
    <nav className="destination-breadcrumbs flex items-center flex-wrap gap-0.5 px-6 py-2.5 text-muted-foreground text-[11px]" aria-label="Destination path">
      <button type="button" className="hover:underline cursor-pointer" onClick={() => { setPath([]); setCursors([]); setSelected(null) }}>{spaceOnly === 'personal' ? 'Personal' : spaceOnly === 'published' ? 'Published' : 'My Library'}</button>
      {path.map((item, index) => <span key={item.id} className="inline-flex items-center"><ChevronRight className="size-[13px] shrink-0" aria-hidden="true" /><button type="button" className="hover:underline cursor-pointer" onClick={() => { setPath(path.slice(0, index + 1)); setCursors([]); setSelected(null) }}>{item.name}</button></span>)}
    </nav>
    <div className="destination-results min-h-[160px] max-h-[330px] overflow-auto mx-6 border-t border-border" aria-live="polite">
      {query.isPending ? <p className="py-6 text-muted-foreground text-xs">Loading destinations…</p> : query.isError ? <div className="py-6 text-muted-foreground text-xs"><p>Could not load this folder.</p><Button variant="link" onClick={() => { void query.refetch() }}>Retry</Button></div>
        : items.length === 0 ? <p className="py-6 text-muted-foreground text-xs">{q ? 'No matching folders or decks.' : 'No folders or decks here yet.'}</p>
          : <ul className="divide-y divide-border">{items.map(node => {
            const item: Destination = { id: node.id, name: node.name, type: node.type as Destination['type'] }
            const eligible = node.type === kind && !excludedIds?.has(node.id)
            const isSelected = selected?.id === node.id
            const folderIcon = node.name === 'Personal' ? 'folder-personal' : node.name === 'Published' ? 'folder-published' : 'folder'
            return <li key={node.id} className={`flex items-stretch border-b border-border transition-colors ${isSelected ? 'bg-accent' : ''}`} data-selected={isSelected}>
              <button type="button" className="destination-choice flex-1 min-w-0 flex items-center gap-3 py-2.5 px-2 text-left cursor-pointer disabled:opacity-65 disabled:cursor-default" disabled={node.type === 'DECK' && !eligible} onClick={() => { if (eligible) setSelected(prev => prev?.id === item.id ? null : item) }} onDoubleClick={() => { if (node.type === 'FOLDER') void navigate(item) }} aria-label={node.type === 'DECK' ? `${node.name} Deck` : node.name} aria-pressed={eligible ? isSelected : undefined}>
                <Icon name={node.type === 'DECK' ? 'collection' : folderIcon} className="size-[30px] shrink-0" /><span className="min-w-0 truncate"><strong className="block text-[13px] font-bold truncate">{node.name}</strong><small className="block text-muted-foreground text-[10px]">{node.type === 'DECK' ? 'Deck' : 'Folder'}</small></span>
              </button>
            </li>
          })}</ul>}
    </div>
    {query.data && (cursors.length > 0 || query.data.next_cursor) && <div className="destination-pages flex justify-between mx-6 py-2">
      <Button variant="link" disabled={!cursors.length} onClick={() => setCursors(cursors.slice(0, -1))}>Previous</Button>
      <Button variant="link" disabled={!query.data.next_cursor} onClick={() => setCursors([...cursors, query.data!.next_cursor!])}>Next</Button>
    </div>}
    {onCreateDeck && <div className="destination-create my-2.5 mx-6">
      {creating ? <form onSubmit={event => { event.preventDefault(); void create() }} className="flex gap-2"><Input aria-label="New deck name" placeholder="Deck name" value={newName} onChange={event => setNewName(event.target.value)} maxLength={255} autoFocus className="min-w-0" /><Button type="submit" disabled={busy || !newName.trim()}>Create and add</Button></form>
        : <Button variant="link" onClick={() => setCreating(true)}>Create a deck in {current.name}</Button>}
    </div>}
    {error && <p className="destination-error text-destructive text-xs px-6 py-2" role="alert">{error}</p>}
    <div className="destination-footer flex items-center gap-2 px-6 py-3.5 border-t border-border mt-auto"><span className="flex-1 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[11px] text-muted-foreground">{selected ? `Selected: ${selected.name}` : canSelectCurrent ? `Current: ${current.name}` : 'Choose a destination'}</span>
      <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button><Button onClick={() => { void confirm() }} disabled={(!selected && !canSelectCurrent) || busy}>{busy ? 'Saving…' : (!selected && canSelectCurrent) ? 'Use this folder' : action}</Button>
    </div>
  </DialogContent></Dialog>
}
