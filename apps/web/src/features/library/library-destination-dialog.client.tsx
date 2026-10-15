'use client'

import { webConfig } from '@/config'

import { useDeferredValue, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslations } from 'next-intl'
import { ChevronRight, Search } from '@/components/artwork/artwork'
import { Icon } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { useServices } from '@/lib/api/services/provider.client'
import type { AccountProfile } from '@/lib/api/account'
import { libraryNodeKind } from '@/features/library/model'

export type Destination = { id: string; name: string; type: 'deck' | 'folder'; space?: 'personal' | 'published' }
type Props = {
  open: boolean; onOpenChange: (open: boolean) => void; profile: AccountProfile
  kind: 'deck' | 'folder'; action: string; onConfirm: (destination: Destination) => Promise<void>
  excludedIds?: ReadonlySet<string>; onCreateDeck?: (parentId: string, name: string, confirmPublication: boolean) => Promise<void>
  spaceOnly?: 'personal' | 'published'
  requirePublicationConfirmation?: boolean
}

export function LibraryDestinationDialog(props: Props) {
  const t = useTranslations('library')
  const tNav = useTranslations('nav')
  const tCommon = useTranslations('common')
  const { open, onOpenChange, profile, kind, action, onConfirm, excludedIds, onCreateDeck, spaceOnly } = props
  const { services, scope } = useServices()
  const root = spaceOnly === 'personal' ? profile.personal_node_id : spaceOnly === 'published' ? profile.published_node_id : profile.library_node_id
  const [path, setPath] = useState<Destination[]>([])
  const current = path.at(-1) ?? { id: root, name: spaceOnly === 'personal' ? t('personal') : spaceOnly === 'published' ? t('published') : tNav('myLibrary'), type: 'folder' as const, space: spaceOnly === 'published' ? 'published' as const : 'personal' as const }
  const [search, setSearch] = useState(''), q = useDeferredValue(search)
  const [cursors, setCursors] = useState<string[]>([])
  const [selected, setSelected] = useState<Destination | null>(null)
  const [creating, setCreating] = useState(false), [newName, setNewName] = useState('')
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const needsConfirmation = props.requirePublicationConfirmation || (creating && current.space === 'published')
  const query = useQuery({ queryKey: [services.mode, scope, 'destination', current.id, q, cursors.at(-1)],
    queryFn: ({ signal }) => services.library.contents(current.id, { q, cursor: cursors.at(-1), limit: webConfig.pagination.picker, includeProgress: false }, signal), enabled: open })
  async function navigate(item: Destination) {
    if (busy) return
    setBusy(true); setError('')
    try {
      const detail = await services.library.metadata(item.id, new AbortController().signal)
      if (detail.owner_id !== profile.id) throw new Error(t('ownDestinationRequired'))
      const rootIndex = detail.breadcrumbs.findIndex(parent => parent.id === root)
      const parents = (rootIndex < 0 ? path : detail.breadcrumbs.slice(rootIndex + 1)).filter(parent => parent.id !== item.id).map(parent => ({ ...parent, type: 'folder' as const, space: detail.space === 'published' ? 'published' as const : 'personal' as const }))
      setPath([...parents, { ...item, space: detail.space === 'published' ? 'published' : 'personal' }]); setSearch(''); setCursors([]); setSelected(null); setCreating(false); setConfirmed(false)
    } catch (cause) { setError(cause instanceof Error ? cause.message : t('couldNotLoadFolder')) }
    finally { setBusy(false) }
  }
  async function selectReference(item: Destination) {
    if (busy) return
    setBusy(true); setError(''); setSelected(null)
    try {
      const detail = await services.library.metadata(item.id, new AbortController().signal)
      if (detail.owner_id !== profile.id) throw new Error(t('ownDestinationRequired'))
      if (detail.type !== 'deck') throw new Error(t('couldNotLoadFolder'))
      setSelected({ ...item, space: detail.space === 'published' ? 'published' : 'personal' })
    } catch (cause) { setError(cause instanceof Error ? cause.message : t('couldNotLoadFolder')) }
    finally { setBusy(false) }
  }
  async function confirm() {
    const target = selected ?? (canSelectCurrent ? current : null)
    if (!target || (props.requirePublicationConfirmation && !confirmed) || busy) return
    setBusy(true); setError('')
    try { await onConfirm(target); onOpenChange(false) }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('couldNotCompleteAction')) }
    finally { setBusy(false) }
  }
  async function create() {
    if (!onCreateDeck || !newName.trim() || (needsConfirmation && !confirmed) || busy) return
    setBusy(true); setError('')
    try { await onCreateDeck(current.id, newName.trim(), confirmed); onOpenChange(false) }
    catch (cause) { setError(cause instanceof Error ? cause.message : t('couldNotSaveNode', { kind: t('kindDeck') })) }
    finally { setBusy(false) }
  }
  const items = query.data?.nodes.filter(node => node.type !== 'reference' || kind === 'deck' && node.reference_id && libraryNodeKind(node)) ?? []
  const canSelectCurrent = kind === 'folder' && current.id !== profile.library_node_id && !excludedIds?.has(current.id)
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="destination-dialog w-[min(560px,calc(100vw-24px))] max-w-none sm:max-w-none max-h-[min(90vh,740px)] flex flex-col gap-0 p-0 bg-background" aria-describedby="destination-description">
    <DialogHeader className="p-0 text-left border-b border-border px-6 pt-[22px] pb-4"><DialogTitle className="text-2xl font-extrabold tracking-[-.03em]">{t('chooseDestination')}</DialogTitle><DialogDescription id="destination-description" className="text-xs text-muted-foreground mt-1">{kind === 'deck' ? t('selectDeckDesc') : t('selectFolderDesc')}</DialogDescription></DialogHeader>
    <div className="destination-search flex items-center gap-2 border border-border mx-6 mt-4 px-2.5"><Search className="size-[17px] shrink-0 text-muted-foreground" aria-hidden="true" /><Input className="border-0 h-9" aria-label={t('searchFoldersAndDecks')} placeholder={t('searchFoldersAndDecks')} value={search} maxLength={200} onChange={event => { setSearch(event.target.value); setCursors([]); setSelected(null) }} /></div>
    <nav className="destination-breadcrumbs flex items-center flex-wrap gap-0.5 px-6 py-2.5 text-muted-foreground text-[11px]" aria-label={t('destinationPath')}>
      <button type="button" className="hover:underline cursor-pointer" disabled={busy} onClick={() => { setPath([]); setSearch(''); setCursors([]); setSelected(null); setCreating(false); setConfirmed(false); setError('') }}>{spaceOnly === 'personal' ? t('personal') : spaceOnly === 'published' ? t('published') : tNav('myLibrary')}</button>
      {path.map((item, index) => <span key={item.id} className="inline-flex items-center"><ChevronRight className="size-[13px] shrink-0" aria-hidden="true" /><button type="button" className="hover:underline cursor-pointer" disabled={busy} onClick={() => { setPath(path.slice(0, index + 1)); setSearch(''); setCursors([]); setSelected(null); setCreating(false); setConfirmed(false); setError('') }}>{item.name}</button></span>)}
    </nav>
    <div className="destination-results min-h-[160px] max-h-[330px] overflow-auto mx-6 border-t border-border" aria-live="polite">
      {query.isPending ? <p className="py-6 text-muted-foreground text-xs">{t('loadingDestinations')}</p> : query.isError ? <div className="py-6 text-muted-foreground text-xs"><p>{t('couldNotLoadFolder')}</p><Button variant="link" onClick={() => { void query.refetch() }}>{tCommon('retry')}</Button></div>
        : items.length === 0 ? <p className="py-6 text-muted-foreground text-xs">{q ? t('noMatchingDestinations') : t('noDestinationsHere')}</p>
          : <ul className="divide-y divide-border">{items.map(node => {
            const item: Destination = { id: node.type === 'reference' ? node.reference_id! : node.id, name: node.name, type: libraryNodeKind(node)! }
            const eligible = item.type === kind && !excludedIds?.has(item.id) && !excludedIds?.has(node.id) && (!node.owner_id || node.owner_id === profile.id)
            const isSelected = selected?.id === item.id
            const folderIcon = node.name === 'Personal' ? 'folder-personal' : node.name === 'Published' ? 'folder-published' : 'folder'
            return <li key={node.id} className={`flex items-stretch border-b border-border transition-colors ${isSelected ? 'bg-accent' : ''}`} data-selected={isSelected}>
              <button type="button" className="destination-choice flex-1 min-w-0 flex items-center gap-3 py-2.5 px-2 text-left cursor-pointer disabled:opacity-65 disabled:cursor-default" disabled={busy || item.type === 'deck' && !eligible} onClick={() => { if (item.type === 'folder' && kind === 'deck') void navigate(item); else if (eligible) { if (node.type === 'reference') void selectReference(item); else { setSelected(prev => prev?.id === item.id ? null : item); setError('') } } }} onDoubleClick={() => { if (item.type === 'folder' && kind === 'folder') void navigate(item) }} aria-label={item.type === 'deck' ? `${node.name} ${t('deck')}` : node.name} aria-pressed={eligible ? isSelected : undefined}>
                <Icon name={item.type === 'deck' ? 'collection' : folderIcon} className="size-[30px] shrink-0" /><span className="min-w-0 truncate"><strong className="block text-[13px] font-bold truncate">{node.name}</strong><small className="block text-muted-foreground text-[10px]">{item.type === 'deck' ? t('deck') : t('folder')}{node.type === 'reference' && ` · ${t('reference')}`}</small></span>
              </button>
            </li>
          })}</ul>}
    </div>
    {query.data && (cursors.length > 0 || query.data.next_cursor) && <div className="destination-pages flex justify-between mx-6 py-2">
      <Button variant="link" disabled={!cursors.length} onClick={() => setCursors(cursors.slice(0, -1))}>{tCommon('previous')}</Button>
      <Button variant="link" disabled={!query.data.next_cursor} onClick={() => setCursors([...cursors, query.data!.next_cursor!])}>{tCommon('next')}</Button>
    </div>}
    {onCreateDeck && <div className="destination-create my-2.5 mx-6">
      {creating ? <form onSubmit={event => { event.preventDefault(); void create() }} className="flex gap-2"><Input aria-label={t('newDeckNameAria')} placeholder={t('deckName')} value={newName} onChange={event => setNewName(event.target.value)} maxLength={255} autoFocus className="min-w-0" /><Button type="submit" disabled={busy || !newName.trim() || (needsConfirmation && !confirmed)}>{t('createAndAdd')}</Button></form>
        : <Button variant="link" onClick={() => setCreating(true)}>{t('createDeckIn', { name: current.name })}</Button>}
    </div>}
    {needsConfirmation && <label className="flex gap-2 px-6 py-2 text-xs"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />{t('makeNewContentPublic')}</label>}
    {error && <p className="destination-error text-destructive text-xs px-6 py-2" role="alert">{error}</p>}
    <div className="destination-footer flex items-center gap-2 px-6 py-3.5 border-t border-border mt-auto"><span className="flex-1 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap text-[11px] text-muted-foreground">{selected ? t('selectedDestination', { name: selected.name }) : canSelectCurrent ? t('currentDestination', { name: current.name }) : t('chooseDestination')}</span>
      <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>{tCommon('cancel')}</Button><Button onClick={() => { void confirm() }} disabled={(!selected && !canSelectCurrent) || busy || (props.requirePublicationConfirmation && !confirmed)}>{busy ? tCommon('saving') : (!selected && canSelectCurrent) ? t('useThisFolder') : action}</Button>
    </div>
  </DialogContent></Dialog>
}
