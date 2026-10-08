'use client'

import { Fragment, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, CalendarDays, Check, Pencil, Share2 } from '@/components/artwork/artwork'
import { toast } from 'sonner'
import { Shape } from '@/components/artwork/artwork'
import { useAccount } from '@/components/application/providers'
import { LibraryNodeIcon } from '@/components/library/library-node-icon'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Breadcrumb, BreadcrumbList, BreadcrumbItem, BreadcrumbLink, BreadcrumbPage, BreadcrumbSeparator } from '@/components/ui/breadcrumb'
import { useServices } from '@/lib/services/provider'
import { publishedHref } from '@/lib/library-model'
import { PublicCollectionActions } from '@/components/library/public-collection-actions'

function PublishedContent({ profileId, rootId, identifier, nodeId, publishedBase, authorName }: { profileId: string; rootId: string; identifier: string; nodeId?: string; publishedBase?: string; authorName: string }) {
  const { services } = useServices()
  const [cursors, setCursors] = useState<string[]>([])
  const cursor = cursors.at(-1)
  const node = useQuery({ queryKey: [services.mode, 'public-node', nodeId], queryFn: ({ signal }) => services.library.publicNode(nodeId!, signal), enabled: !!nodeId })
  const safeNode = nodeId ? node.data?.owner_id === profileId && node.data.space === 'PUBLISHED' : true
  const kind = nodeId ? node.data?.target?.type ?? node.data?.type : 'FOLDER'
  const contents = useQuery({ queryKey: [services.mode, 'public-contents', nodeId ?? rootId, cursor], queryFn: ({ signal }) => services.library.publicContents(nodeId ?? rootId, cursor, signal), enabled: safeNode && kind === 'FOLDER' })
  const meanings = useQuery({ queryKey: [services.mode, 'public-meanings', nodeId, cursor], queryFn: ({ signal }) => services.library.publicMeanings(nodeId!, cursor, signal), enabled: safeNode && kind === 'DECK' })
  const base = publishedBase ?? `/u/${encodeURIComponent(identifier)}`
  const parent = node.data?.breadcrumbs.at(-1)
  const back = parent && parent.id !== rootId ? `${base}/${encodeURIComponent(parent.id)}` : base
  const ancestors = node.data?.breadcrumbs.filter(item => item.id !== rootId) ?? []
  const page = kind === 'DECK' ? meanings.data : contents.data
  if (nodeId && node.isPending) return <p className="py-6 text-muted-foreground" role="status">Loading collection…</p>
  if (node.isError || !safeNode) return <p className="py-6 text-muted-foreground" role="alert">This collection is unavailable on this profile.</p>
  if (kind === 'REFERENCE') return <p className="py-6 text-muted-foreground" role="alert">This published reference is no longer available.</p>
  return <section className="mt-8" aria-labelledby="profile-published-title">
    {publishedBase && <Breadcrumb className="mb-4 text-xs"><BreadcrumbList><BreadcrumbItem><BreadcrumbLink asChild><Link href={`/u/${encodeURIComponent(identifier)}`}>{authorName}</Link></BreadcrumbLink></BreadcrumbItem><BreadcrumbSeparator /><BreadcrumbItem>{nodeId ? <BreadcrumbLink asChild><Link href={base}>Published</Link></BreadcrumbLink> : <BreadcrumbPage>Published</BreadcrumbPage>}</BreadcrumbItem>{ancestors.map(item => <Fragment key={item.id}><BreadcrumbSeparator /><BreadcrumbItem><BreadcrumbLink asChild><Link href={`${base}/${encodeURIComponent(item.id)}`}>{item.name}</Link></BreadcrumbLink></BreadcrumbItem></Fragment>)}{nodeId && <><BreadcrumbSeparator /><BreadcrumbItem><BreadcrumbPage>{node.data?.name}</BreadcrumbPage></BreadcrumbItem></>}</BreadcrumbList></Breadcrumb>}
    <div className="flex justify-between border-b border-border pb-4 [&_h2]:text-[22px] [&_h2]:font-extrabold [&_h2]:tracking-tight [&_p]:mt-1 [&_p]:text-[13px] [&_p]:text-muted-foreground"><div>{nodeId && <Link href={back} className="mb-3 inline-flex items-center gap-1.5 text-xs text-art-blue hover:underline [&_svg]:size-3.5"><ArrowLeft aria-hidden="true" /> {parent && parent.id !== rootId ? parent.name : 'Published'}</Link>}<h2 id="profile-published-title">{nodeId ? node.data?.name : 'Published collections'}</h2><p>{nodeId ? node.data?.description || (kind === 'DECK' ? 'Meanings in this deck.' : 'Explore this folder.') : 'Vocabulary this author chose to share.'}</p></div></div>
    {nodeId && node.data?.role === 'NORMAL' && <PublicCollectionActions nodeId={nodeId} name={node.data.name} targetId={node.data.target?.id} ownerId={profileId} />}
    {contents.isError || meanings.isError ? <div className="py-6 text-muted-foreground" role="alert"><p>Could not load this collection.</p><Button variant="outline" onClick={() => { void (kind === 'DECK' ? meanings.refetch() : contents.refetch()) }}>Retry</Button></div>
      : kind === 'DECK' ? meanings.isPending ? <p className="py-6 text-muted-foreground" role="status">Loading meanings…</p> : <div>{meanings.data?.senses.map((sense, index) => <article key={sense.sense_id} className="grid grid-cols-[50px_1fr] gap-4 border-b border-border px-1 py-4.5 [&>span]:text-[23px] [&>span]:font-extrabold [&>span]:text-muted-foreground [&_h3]:text-lg [&_h3]:font-extrabold [&_p]:mt-0.5 [&_p]:mb-2 [&_p]:text-xs [&_p]:capitalize [&_p]:text-muted-foreground [&_strong]:block [&_strong]:text-sm [&_small]:mt-1.5 [&_small]:block [&_small]:text-xs [&_small]:text-muted-foreground"><span>{String(index + 1 + cursors.length * 12).padStart(2, '0')}</span><div><h3>{sense.lemma}</h3><p>{sense.pos}{sense.cefr_level ? ` · ${sense.cefr_level}` : ''}</p><strong>{sense.definition ?? 'Definition unavailable'}</strong>{sense.examples[0] && <small>{sense.examples[0].text}</small>}</div></article>)}{meanings.data?.senses.length === 0 && <p className="py-6 text-muted-foreground">This deck has no published meanings yet.</p>}</div>
      : contents.isPending ? <p className="py-6 text-muted-foreground" role="status">Loading published collections…</p> : <div className="grid grid-cols-2 gap-2.5 pt-4.5 max-[650px]:grid-cols-1">{contents.data?.nodes.map((item, index) => <Link key={item.id} href={item.owner_id && item.owner_id !== profileId ? publishedBase ? publishedHref(item.owner_id, item.id) : `/u/${encodeURIComponent(item.owner_id)}/${encodeURIComponent(item.id)}` : `${base}/${encodeURIComponent(item.id)}`} className="relative grid min-h-[110px] grid-cols-[34px_minmax(0,1fr)_18px] items-start gap-3.5 overflow-hidden border border-border p-5 hover:border-art-blue [&>svg]:size-7 [&_strong]:block [&_strong]:text-[15px] [&_strong]:font-extrabold [&_small]:mt-1 [&_small]:block [&_small]:max-w-[42ch] [&_small]:text-xs [&_small]:text-muted-foreground"><LibraryNodeIcon node={item} /><span><strong>{item.name}</strong><small>{item.type === 'FOLDER' ? 'Folder' : item.type === 'DECK' ? 'Deck' : 'Reference'}{item.description ? ` · ${item.description}` : ''}</small></span><ArrowRight aria-hidden="true" /><Shape name={index % 3 === 0 ? 'circle' : index % 3 === 1 ? 'square' : 'triangle'} className="pointer-events-none absolute -right-4.5 -bottom-9.5 size-[72px]" /></Link>)}{contents.data?.nodes.length === 0 && <p className="py-6 text-muted-foreground">No published collections here yet.</p>}</div>}
    {(page?.next_cursor || cursors.length > 0) && <div className="flex items-center justify-end gap-3 py-4.5 text-xs"><Button variant="outline" disabled={!cursors.length} onClick={() => setCursors(cursors.slice(0, -1))}>Previous</Button><span>Page {cursors.length + 1}</span><Button variant="outline" disabled={!page?.next_cursor} onClick={() => setCursors([...cursors, page!.next_cursor!])}>Next</Button></div>}
  </section>
}

export function PublicProfilePage({ identifier, nodeId, publishedBase }: { identifier: string; nodeId?: string; publishedBase?: string }) {
  const { services, scope } = useServices(), account = useAccount(), queryClient = useQueryClient(), router = useRouter()
  const query = useQuery({ queryKey: [services.mode, scope, 'public-profile', identifier], queryFn: ({ signal }) => services.account.publicProfile(identifier, signal) })
  const [editing, setEditing] = useState(false), [handle, setHandle] = useState(''), [bio, setBio] = useState(''), [saving, setSaving] = useState(false)
  const profile = query.data, own = !!profile && account.profile?.id === profile.id
  async function share() {
    if (!profile) return
    const url = `${location.origin}/u/${encodeURIComponent(profile.handle || profile.id)}`
    try { await navigator.clipboard.writeText(url); toast.success('Profile link copied') }
    catch { toast.error('Could not copy the link. Copy the address from your browser instead.') }
  }
  async function save() {
    if (!profile) return
    setSaving(true)
    try {
      const patch = { bio: bio.trim() || null, ...(handle !== profile.handle && handle ? { handle } : {}) }
      const next = await services.account.updateProfile(patch, new AbortController().signal)
      queryClient.setQueryData([services.mode, scope, 'account'], next)
      await queryClient.invalidateQueries({ queryKey: [services.mode, scope, 'public-profile'] })
      setEditing(false)
      if (identifier === profile.handle && next.handle !== profile.handle) router.replace(`/u/${encodeURIComponent(next.handle || next.id)}`)
      toast.success('Public profile updated')
    } catch (error) { toast.error(error instanceof Error ? error.message : 'Could not save your profile. Please retry.') }
    finally { setSaving(false) }
  }
  if (query.isPending) return <div className="w-full py-6 text-muted-foreground" role="status">Loading profile…</div>
  if (query.isError || !profile) return <div className="w-full py-6 text-muted-foreground" role="alert"><h1 className="text-2xl font-extrabold tracking-tight">Profile unavailable</h1><p className="mt-2 mb-4">This profile could not be found.</p><Button variant="outline" onClick={() => { void query.refetch() }}>Try again</Button></div>
  return <div className="w-full">
    <header className="relative grid min-h-[204px] grid-cols-[160px_minmax(0,1fr)_auto] gap-7 overflow-hidden border border-border max-[850px]:grid-cols-[130px_1fr] max-[850px]:gap-5 max-[650px]:grid-cols-[90px_1fr] max-[650px]:gap-3.5"><div className="flex flex-wrap content-center justify-center border-r border-border [&_svg]:size-16 [&_svg:first-child]:size-32 max-[850px]:[&_svg]:size-[50px] max-[850px]:[&_svg:first-child]:size-[100px] max-[650px]:[&_svg]:size-[38px] max-[650px]:[&_svg:first-child]:size-[76px]" aria-hidden="true"><Shape name="circle" /><Shape name="square" /><Shape name="triangle" /></div><div className="z-1 self-center py-6 max-[650px]:py-5 max-[650px]:pr-3 max-[650px]:pb-2 [&_h1]:leading-[1.12] [&_h1]:font-extrabold [&_h1]:tracking-[-.03em]"><h1 className="text-[clamp(2.25rem,2.6vw,3rem)] font-extrabold leading-[1.12] tracking-[-.03em] max-[700px]:text-[34px]">{profile.display_name || profile.handle || 'Pycil learner'}<span className="text-art-red" aria-hidden="true">.</span></h1>{profile.handle && <p className="mt-1 text-xl">@{profile.handle}</p>}<p className="my-3 max-w-[60ch] text-muted-foreground">{profile.bio || (own ? 'Add a short introduction to your public profile.' : 'This learner has not added an introduction yet.')}</p><p className="mt-4.5 flex items-center gap-1.5 text-xs [&_svg]:size-4"><CalendarDays aria-hidden="true" /> Joined {new Intl.DateTimeFormat('en', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(profile.joined_at))}</p></div><div className="z-1 flex self-start gap-2 p-5.5 [&_svg]:size-4 max-[850px]:col-start-2 max-[850px]:p-0 max-[850px]:pb-5 max-[650px]:col-[1/3] max-[650px]:px-3.5 max-[650px]:pb-4.5 max-[410px]:flex-wrap">{own && <Button variant="outline" onClick={() => { setHandle(profile.handle || ''); setBio(profile.bio || ''); setEditing(true) }}><Pencil aria-hidden="true" /> Edit profile</Button>}<Button variant="outline" onClick={share}><Share2 aria-hidden="true" /> Share profile</Button></div><div className="pointer-events-none absolute -right-9 -bottom-12 flex opacity-85 [&_svg]:size-[100px] [&_svg+svg]:-ml-9.5 [&_svg+svg]:translate-y-[30px] max-[850px]:opacity-35" aria-hidden="true"><Shape name="circle" /><Shape name="square" /></div></header>
    {editing && <section className="my-5 grid max-w-[680px] gap-3 border border-border p-6 [&_h2]:text-xl [&_h2]:font-extrabold [&_p]:text-xs [&_p]:text-muted-foreground [&_small]:text-xs [&_small]:text-muted-foreground [&_label]:grid [&_label]:gap-1.5 [&_label]:text-[13px] [&_label]:font-extrabold" aria-labelledby="profile-edit-title"><div><h2 id="profile-edit-title">Edit public profile</h2><p>Your handle and bio are visible to everyone. Your name comes from your account.</p></div><label>Handle<Input value={handle} maxLength={30} onChange={event => setHandle(event.target.value)} aria-describedby="profile-handle-help" /></label><small id="profile-handle-help">Optional until set. Use 3–30 lowercase letters, numbers or underscores; start with a letter.</small><label>Bio<Textarea value={bio} maxLength={500} rows={3} onChange={event => setBio(event.target.value)} /></label><div className="flex justify-end gap-2 [&_svg]:size-4"><Button variant="outline" onClick={() => setEditing(false)}>Cancel</Button><Button disabled={saving || (handle ? !/^[a-z][a-z0-9_]{2,29}$/.test(handle) : !!profile.handle)} onClick={save}>{saving ? 'Saving…' : <><Check aria-hidden="true" /> Save profile</>}</Button></div></section>}
    <PublishedContent key={nodeId ?? 'root'} profileId={profile.id} rootId={profile.published_node_id} identifier={profile.handle || profile.id} nodeId={nodeId} publishedBase={publishedBase} authorName={profile.display_name || profile.handle || 'Author'} />
  </div>
}
