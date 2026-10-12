'use client'

import { useQuery } from '@tanstack/react-query'
import { useAccount } from '@/components/application/providers'
import { useServices } from '@/lib/services/provider'
import { useTranslations } from 'next-intl'

export function LibraryAuthor({ ownerId }: { ownerId?: string }) {
  const account = useAccount(), { services, scope } = useServices()
  const t = useTranslations('library')
  const mine = ownerId === account.profile?.id
  const query = useQuery({ queryKey: [services.mode, scope, 'public-author', ownerId], queryFn: ({ signal }) => services.account.publicProfile(ownerId!, signal), enabled: Boolean(ownerId && !mine), staleTime: 300000 })
  return <span className="inline-block text-[11px] leading-[1.4] text-muted-foreground max-[767px]:group-data-[view=list]:col-start-1">{t('byAuthor', { name: mine ? t('me') : query.data?.display_name ?? (query.isError ? t('unknownAuthor') : '…') })}</span>
}
