'use client'

import { Fragment } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Globe, Lock, ArrowUpLeft } from '@/components/artwork/artwork'
import { toast } from 'sonner'
import { Motif } from '@/components/artwork/artwork'
import { Badge } from '@/components/ui/badge'
import { Breadcrumb, BreadcrumbList, BreadcrumbItem, BreadcrumbLink, BreadcrumbPage, BreadcrumbSeparator } from '@/components/ui/breadcrumb'
import { libraryHref, libraryMotif, nodeHref, publishedHref, type LibraryDetails } from '@/lib/library-model'
import type { AccountProfile } from '@/lib/api'
import { LibraryAuthor } from './library-author'
import { LibraryNodeActions } from './library-node-actions'

export function LibraryHeader({ node, profile, editable }: { node: LibraryDetails; profile: AccountProfile; editable: boolean }) {
  const router = useRouter()
  const published = node.space === 'PUBLISHED'
  const rootId = published ? profile.published_node_id : profile.personal_node_id
  const rootHref = published ? publishedHref(profile.id, rootId) : libraryHref(rootId)
  const parents = node.breadcrumbs.filter(parent => parent.id !== profile.library_node_id && parent.id !== rootId)
  const title = node.id === profile.personal_node_id ? 'Personal' : node.name
  async function copyLink() {
    try { await navigator.clipboard.writeText(new URL(nodeHref(node), location.origin).href); toast.success('Link copied') }
    catch { toast.error('Could not copy the link. Copy it from the address bar.') }
  }
  return <header className="grid grid-cols-[minmax(0,1.3fr)_1fr_1fr_1fr] max-[767px]:grid-cols-1 items-stretch min-h-[124px] max-[767px]:min-h-0 max-[767px]:py-4 border-b border-border [&_h1]:leading-[1.12]">
    <div className="col-span-3 max-[767px]:col-span-1 min-w-0 flex flex-col justify-center py-4 pr-6 max-[767px]:p-0">
      <Breadcrumb className="mb-1 text-xs"><BreadcrumbList>
        <BreadcrumbItem>
          {node.id === rootId && !published ? <BreadcrumbPage>Personal</BreadcrumbPage> : <BreadcrumbLink asChild><Link href={published ? `/u/${encodeURIComponent(profile.id)}` : libraryHref(profile.personal_node_id)}>{published ? 'Me' : 'Personal'}</Link></BreadcrumbLink>}
        </BreadcrumbItem>
        {published && <><BreadcrumbSeparator /><BreadcrumbItem>{node.id === rootId ? <BreadcrumbPage>Published</BreadcrumbPage> : <BreadcrumbLink asChild><Link href={rootHref}>Published</Link></BreadcrumbLink>}</BreadcrumbItem></>}
        {parents.map(parent => <Fragment key={parent.id}><BreadcrumbSeparator /><BreadcrumbItem><BreadcrumbLink asChild><Link href={published ? publishedHref(profile.id, parent.id) : libraryHref(parent.id)}>{parent.name}</Link></BreadcrumbLink></BreadcrumbItem></Fragment>)}
        {node.id !== rootId && <><BreadcrumbSeparator /><BreadcrumbItem><BreadcrumbPage>{node.name}</BreadcrumbPage></BreadcrumbItem></>}
      </BreadcrumbList></Breadcrumb>
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-[clamp(2.25rem,2.6vw,3rem)] font-extrabold leading-[1.12] tracking-[-.03em] max-[700px]:text-[34px] overflow-wrap-anywhere text-balance">{title}<span className="text-art-red" aria-hidden="true">.</span></h1>
        {node.space !== 'LIBRARY' && <LibraryNodeActions node={node} space={node.space}
          allowEdit={editable} onCopyLink={() => { void copyLink() }} onDeleted={editable ? () => router.push(node.breadcrumbs.at(-1) ? published ? publishedHref(profile.id, node.breadcrumbs.at(-1)!.id) : libraryHref(node.breadcrumbs.at(-1)!.id) : rootHref) : undefined} className="relative top-auto right-auto" />}
      </div>
      {node.description && <p className="text-muted-foreground leading-relaxed text-sm max-w-[58ch] mt-1">{node.description}</p>}
      <div className={`${node.role !== 'NORMAL' ? 'hidden' : 'flex'} flex-wrap items-center gap-3 mt-2 [&_a]:inline-flex [&_a]:items-center [&_a]:gap-1.5 [&_a]:text-xs [&_a]:underline [&_a]:underline-offset-4 [&_a_svg]:size-3.5`}><Badge variant="outline">{node.space === 'PUBLISHED' ? <Globe aria-hidden="true" /> : <Lock aria-hidden="true" />}{node.space === 'PUBLISHED' ? 'Published' : 'Personal'}</Badge>
        {node.type === 'REFERENCE' && <Badge variant="secondary">Reference</Badge>}
        {node.role === 'NORMAL' && <LibraryAuthor ownerId={node.owner_id} />}
        {node.target && <Link href={nodeHref(node.target)}>Open source<ArrowUpLeft aria-hidden="true" /></Link>}
      </div>
    </div>
    <div className="library-header-art header-motif-art col-span-1 max-[767px]:hidden" aria-hidden="true"><Motif name={libraryMotif(node.id)} /></div>
  </header>
}
