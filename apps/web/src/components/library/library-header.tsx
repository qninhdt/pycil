'use client'

import { Fragment } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Globe, Lock, ArrowUpLeft } from '@/components/artwork/artwork'
import { toast } from 'sonner'
import { Motif } from '@/components/artwork/artwork'
import { Badge } from '@/components/ui/badge'
import { Breadcrumb, BreadcrumbList, BreadcrumbItem, BreadcrumbLink, BreadcrumbPage, BreadcrumbSeparator } from '@/components/ui/breadcrumb'
import { libraryHref, libraryMotif, nodeHref, publishedHref, type LibraryDetails } from '@/lib/library-model'
import type { AccountProfile } from '@/lib/api'
import { useQuery } from '@tanstack/react-query'
import { useServices } from '@/lib/services/provider'
import { LibraryAuthor } from './library-author'
import { LibraryNodeActions } from './library-node-actions'

export function LibraryHeader({ node, profile, editable }: { node: LibraryDetails; profile: AccountProfile; editable: boolean }) {
  const t = useTranslations('library')
  const router = useRouter()
  const { services, scope } = useServices()
  const published = node.space === 'PUBLISHED'
  const mine = node.owner_id === profile.id
  const authorQuery = useQuery({
    queryKey: [services.mode, scope, 'public-author', node.owner_id],
    queryFn: ({ signal }) => services.account.publicProfile(node.owner_id, signal),
    enabled: Boolean(published && !mine && node.owner_id),
    staleTime: 300000,
  })
  const authorName = mine ? t('me') : (authorQuery.data?.display_name ?? node.owner_id ?? 'Public')
  const rootId = published ? (mine ? profile.published_node_id : authorQuery.data?.published_node_id ?? node.breadcrumbs[0]?.id) : profile.personal_node_id
  const rootHref = published ? publishedHref(node.owner_id) : libraryHref(rootId)
  const parents = node.breadcrumbs.filter(parent => parent.id !== node.id && parent.id !== profile.library_node_id && parent.id !== rootId)
  const title = node.id === profile.personal_node_id ? t('personal') : node.name
  async function copyLink() {
    try { await navigator.clipboard.writeText(new URL(nodeHref(node), location.origin).href); toast.success(t('linkCopied')) }
    catch { toast.error(t('couldNotCopyLink')) }
  }
  return <header className="grid grid-cols-[minmax(0,1.3fr)_1fr_1fr_1fr] max-[767px]:grid-cols-1 items-stretch min-h-[124px] max-[767px]:min-h-0 max-[767px]:py-4 border-b border-border [&_h1]:leading-[1.12]">
    <div className="col-span-3 max-[767px]:col-span-1 min-w-0 flex flex-col justify-center py-4 pr-6 max-[767px]:p-0">
      <Breadcrumb className="mb-1 text-xs"><BreadcrumbList>
        <BreadcrumbItem>
          {node.id === rootId && !published ? <BreadcrumbPage>{t('personal')}</BreadcrumbPage> : <BreadcrumbLink asChild><Link href={published ? `/u/${encodeURIComponent(node.owner_id)}` : libraryHref(profile.personal_node_id)}>{published ? authorName : t('personal')}</Link></BreadcrumbLink>}
        </BreadcrumbItem>
        {published && <><BreadcrumbSeparator /><BreadcrumbItem>{node.id === rootId ? <BreadcrumbPage>{t('published')}</BreadcrumbPage> : <BreadcrumbLink asChild><Link href={rootHref}>{t('published')}</Link></BreadcrumbLink>}</BreadcrumbItem></>}
        {parents.map(parent => <Fragment key={parent.id}><BreadcrumbSeparator /><BreadcrumbItem><BreadcrumbLink asChild><Link href={published ? publishedHref(node.owner_id, parent.id) : libraryHref(parent.id)}>{parent.name}</Link></BreadcrumbLink></BreadcrumbItem></Fragment>)}
        {node.id !== rootId && <><BreadcrumbSeparator /><BreadcrumbItem><BreadcrumbPage>{node.name}</BreadcrumbPage></BreadcrumbItem></>}
      </BreadcrumbList></Breadcrumb>
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-[clamp(1.75rem,2.4vw,3rem)] font-extrabold leading-[1.15] tracking-[-.03em] max-[767px]:text-2xl max-[767px]:leading-tight overflow-wrap-anywhere text-balance">{title}<span className="text-art-red" aria-hidden="true">.</span></h1>
        {node.space !== 'LIBRARY' && <LibraryNodeActions node={node} space={node.space}
          allowEdit={editable} onCopyLink={() => { void copyLink() }} onDeleted={editable ? () => router.push(parents.at(-1) ? published ? publishedHref(profile.id, parents.at(-1)!.id) : libraryHref(parents.at(-1)!.id) : rootHref) : undefined} className="relative top-auto right-auto" />}
      </div>
      {node.description && <p className="text-muted-foreground leading-relaxed text-sm max-w-[58ch] mt-1">{node.description}</p>}
      <div className={`${node.role !== 'NORMAL' ? 'hidden' : 'flex'} flex-wrap items-center gap-3 mt-2 [&_a]:inline-flex [&_a]:items-center [&_a]:gap-1.5 [&_a]:text-xs [&_a]:underline [&_a]:underline-offset-4 [&_a_svg]:size-3.5`}><Badge variant="outline">{node.space === 'PUBLISHED' ? <Globe aria-hidden="true" /> : <Lock aria-hidden="true" />}{node.space === 'PUBLISHED' ? t('published') : t('personal')}</Badge>
        {node.type === 'REFERENCE' && <Badge variant="secondary">{t('reference')}</Badge>}
        {node.role === 'NORMAL' && <LibraryAuthor ownerId={node.owner_id} />}
        {node.target && <Link href={nodeHref(node.target)}>{t('openSource')}<ArrowUpLeft aria-hidden="true" /></Link>}
      </div>
    </div>
    <div className="library-header-art header-motif-art col-span-1 max-[767px]:hidden" aria-hidden="true"><Motif name={libraryMotif(node.id)} /></div>
  </header>
}
