'use client'

import { publicAuthorQuery } from '@/features/account/public-queries'
import { useQuery } from '@tanstack/react-query'
import { useAccount } from '@/features/account/account.client'
import { useServices } from '@/lib/api/services/provider.client'
import { useTranslations } from 'next-intl'

export function LibraryAuthor({ ownerId }: { ownerId?: string }) {
  const account = useAccount(), { services, scope } = useServices()
  const t = useTranslations('library')
  const mine = ownerId === account.profile?.id
  const query = useQuery({ ...publicAuthorQuery(services, scope, ownerId ?? ''), enabled: Boolean(ownerId && !mine) })
  return <span className="inline-block text-[11px] leading-[1.4] text-muted-foreground max-[767px]:group-data-[view=list]:col-start-1">{t('byAuthor', { name: mine ? t('me') : query.data?.display_name ?? (query.isError ? t('unknownAuthor') : '…') })}</span>
}
