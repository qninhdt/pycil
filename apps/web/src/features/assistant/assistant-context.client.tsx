'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Icon } from '@/components/artwork/artwork'
import { useAccount } from '@/features/account/account.client'
import { useAssistantContext } from '@/features/assistant/current-view.client'
import { useLibraryNode } from '@/features/library/use-library.client'
import { isDeck, libraryHref, nodeHref, publishedHref } from '@/features/library/model'
import { cn } from '@/lib/utils'
import { useQuery } from '@tanstack/react-query'
import { useServices } from '@/lib/api/services/provider.client'
import { progressQuery } from '@/features/library/queries'

export function AssistantContextTab() {
  const pathname = usePathname() ?? ''
  const t = useTranslations('library')
  const account = useAccount()
  const profile = account.profile

  const { view } = useAssistantContext()
  const resolvedNodeId = view?.path === pathname ? view.node_id : undefined

  const { data: node } = useLibraryNode(resolvedNodeId || '')
  const { services, scope } = useServices()
  const { data: summary } = useQuery({ ...progressQuery(services, scope, resolvedNodeId || ''),
    enabled: !!node && node.reference_available !== false && account.status === 'ready' })

  // Only render when currently inside an active deck or folder
  if (!node) return null

  const deck = isDeck(node)
  const badgeType = deck ? 'deck' : 'folder'
  const iconName = deck ? ('collection' as const) : ('folder' as const)
  const stats = deck
    ? summary
      ? t('wordsTotal', { count: summary.total })
      : null
    : summary
      ? `${t('deckCount', { count: summary.reachable_decks })} · ${t('wordsTotal', { count: summary.total })}`
      : null
  const href =
    node.id === profile?.published_node_id
      ? publishedHref()
      : node.id === profile?.personal_node_id
        ? libraryHref()
        : nodeHref(node, undefined, profile?.id)

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
