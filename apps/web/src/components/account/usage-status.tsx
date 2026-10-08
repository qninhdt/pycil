'use client'

import { useQuery } from '@tanstack/react-query'
import { useAccount } from '@/components/application/providers'
import { Button } from '@/components/ui/button'
import { useServices } from '@/lib/services/provider'

export function UsageStatus() {
  const { services, scope } = useServices(), account = useAccount()
  const usage = useQuery({ queryKey: [services.mode, scope, 'usage'], queryFn: ({ signal }) => services.account.usage(signal) })
  return <div className="ai-plan-banner" role="status">
    <div className="ai-plan-info"><span><strong>{account.profile?.plan.toUpperCase() === 'PRO' ? 'Pro' : 'Free'} plan:</strong>{' '}
      {usage.isPending ? 'Loading AI allowance…' : usage.isError ? 'AI allowance unavailable.' : `${usage.data.remaining_units.toLocaleString()} of ${usage.data.allowance_units.toLocaleString()} AI units remaining.`}
    </span></div>
    {usage.isError ? <Button variant="link" onClick={() => { void usage.refetch() }}>Retry allowance</Button> : usage.data && <span className="ai-plan-badge">Resets {new Date(usage.data.period_end).toLocaleDateString()}</span>}
  </div>
}
