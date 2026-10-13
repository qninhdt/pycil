'use client'

import { useTranslations } from 'next-intl'
import { Icon } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import type { Approval } from '@/lib/api/assistant'

export function ApprovalPanel({ approvals, busy = false, onDecision }: { approvals: Approval[]; busy?: boolean; onDecision: (approve: boolean) => void }) {
  const t = useTranslations('assistant')
  if (!approvals.length) return null
  return <section className="ai-approval" aria-label={t('pendingChanges')}>
    <h3 className="ai-approval-heading"><Icon name="triangle-alert" variant="control" tone="color" />{t('reviewChanges')}</h3>
    {approvals.flatMap(approval => approval.action_requests).map((action, index) => <div className="ai-approval-action" key={index}><strong>{action.description || action.name.replaceAll('_', ' ')}</strong><pre>{JSON.stringify(action.args, null, 2)}</pre></div>)}
    <div className="ai-approval-buttons"><Button onClick={() => onDecision(true)} disabled={busy}>{t('approveChanges')}<Icon name="check" variant="control" /></Button><Button variant="outline" onClick={() => onDecision(false)} disabled={busy}>{t('reject')}</Button></div>
  </section>
}

