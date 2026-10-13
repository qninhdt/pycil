'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { useQuery } from '@tanstack/react-query'
import { Icon } from '@/components/artwork/artwork'
import { useAccount } from '@/components/application/providers'
import { useServices } from '@/lib/services/provider'
import { useLibraryNode } from '@/hooks/use-library'
import { isDeck, libraryHref, nodeHref, publishedHref } from '@/lib/library-model'
import { cn } from '@/lib/utils'

export function AssistantContextTab() {
  const pathname = usePathname() ?? ''
  const t = useTranslations('library')
  const account = useAccount()
  const profile = account.profile
  const { services, scope } = useServices()

  const [searchNode, setSearchNode] = useState<string | null>(null)
  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      const node = new URLSearchParams(window.location.search).get('node')
      setSearchNode(node)
    } catch {
      setSearchNode(null)
    }
  }, [pathname])

  // Resolve active deck or folder when inside personal or published library
  const personalSubMatch = pathname.match(/^\/app\/personal\/([^/]+)/)
  const isPersonalRoot = pathname === '/app/personal'

  const publishedSubMatch = pathname.match(/^\/app\/u\/([^/]+)\/published\/([^/]+)/)
  const publishedRootMatch = pathname.match(/^\/app\/u\/([^/]+)\/published\/?$/)

  const publicSubMatch = pathname.match(/^\/u\/([^/]+)\/([^/]+)/)
  const publicRootMatch = pathname.match(/^\/u\/([^/]+)\/?$/)

  const isOwn = (identifier: string) =>
    identifier === 'me' ||
    (Boolean(profile?.id) && identifier === profile?.id) ||
    (Boolean(profile?.handle) && identifier === profile?.handle)

  // Determine if viewing another user's published root
  const otherUser =
    (publishedRootMatch && !isOwn(publishedRootMatch[1]) ? publishedRootMatch[1] : null) ||
    (publicRootMatch && !isOwn(publicRootMatch[1]) ? publicRootMatch[1] : null)

  const otherProfileQuery = useQuery({
    queryKey: [services.mode, scope, 'public-profile', otherUser],
    queryFn: ({ signal }) => services.account.publicProfile(otherUser!, signal),
    enabled: Boolean(otherUser),
  })

  let resolvedNodeId: string | null = null
  if (searchNode) {
    resolvedNodeId = searchNode
  } else if (personalSubMatch) {
    resolvedNodeId = personalSubMatch[1]
  } else if (isPersonalRoot) {
    resolvedNodeId = profile?.personal_node_id ?? null
  } else if (publishedSubMatch) {
    resolvedNodeId = publishedSubMatch[2]
  } else if (publishedRootMatch) {
    resolvedNodeId = otherUser
      ? otherProfileQuery.data?.published_node_id ?? null
      : profile?.published_node_id ?? null
  } else if (publicSubMatch) {
    resolvedNodeId = publicSubMatch[2]
  } else if (publicRootMatch) {
    resolvedNodeId = otherUser
      ? otherProfileQuery.data?.published_node_id ?? null
      : profile?.published_node_id ?? null
  }

  const { data: node } = useLibraryNode(resolvedNodeId || '')

  // Only render when currently inside an active deck or folder
  if (!node) return null

  const deck = isDeck(node)
  const badgeType = deck ? 'deck' : 'folder'
  const iconName = deck ? ('collection' as const) : ('folder' as const)
  const stats = deck
    ? node.summary
      ? t('wordsTotal', { count: node.summary.total })
      : null
    : node.summary
      ? `${t('deckCount', { count: node.summary.reachable_decks ?? 0 })} · ${t('wordsTotal', { count: node.summary.total ?? 0 })}`
      : null
  const href =
    node.id === profile?.published_node_id
      ? publishedHref(node.owner_id)
      : node.id === profile?.personal_node_id
        ? libraryHref()
        : nodeHref(node)

  return (
    <div className="ai-context-tab" role="region" aria-label={`Current ${badgeType.toLowerCase()}: ${node.name}`}>
      <div className="ai-context-tab-left">
        <Icon name={iconName} tone="color" className="size-3.5 shrink-0" />
        <span
          className={cn(
            'ai-context-badge',
            deck ? 'ai-context-badge-deck' : 'ai-context-badge-folder',
          )}
        >
          {badgeType}
        </span>
        <span className="ai-context-title" title={node.name}>
          {node.name}
        </span>
      </div>
      <div className="ai-context-tab-right">
        {stats && <span className="ai-context-stats">{stats}</span>}
        {href && (
          <Link href={href} className="ai-context-link" aria-label={`Open ${node.name}`}>
            <Icon name="arrow-up-right" variant="control" className="size-3 shrink-0" />
          </Link>
        )}
      </div>
    </div>
  )
}
