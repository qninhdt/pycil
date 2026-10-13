'use client'

import { useTranslations } from 'next-intl'
import { useQuery } from '@tanstack/react-query'
import { useAccount } from '@/components/application/providers'
import { Button } from '@/components/ui/button'
import { useServices } from '@/lib/services/provider'

export function UsageStatus() {
  const t = useTranslations('library')
  const { services, scope } = useServices(), account = useAccount()
  const usage = useQuery({ queryKey: [services.mode, scope, 'usage'], queryFn: ({ signal }) => services.account.usage(signal) })
  return <div className="ai-plan-banner" role="status">
    <div className="ai-plan-info"><span><strong>{account.profile?.plan.toUpperCase() === 'pro' ? t('proPlanLabel') : t('freePlanLabel')}</strong>{' '}
      {usage.isPending ? t('loadingAiAllowance') : usage.isError ? t('aiAllowanceUnavailable') : t('aiUnitsRemaining', { remaining: usage.data.remaining_units.toLocaleString(), allowance: usage.data.allowance_units.toLocaleString() })}
    </span></div>
    {usage.isError ? <Button variant="link" onClick={() => { void usage.refetch() }}>{t('retryAllowance')}</Button> : usage.data && <span className="ai-plan-badge">{t('resetsDate', { date: new Date(usage.data.period_end).toLocaleDateString() })}</span>}
  </div>
}
