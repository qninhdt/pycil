'use client'

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { useAccount } from '@/features/account/account.client'
import { useServices } from '@/lib/api/services/provider.client'
import { useTranslations } from 'next-intl'

export function AppShellStatus() {
  const account = useAccount()
  const { services } = useServices()
  const tNav = useTranslations('nav')
  const tCommon = useTranslations('common')

  return (
    <>
      {services.notice && (
        <p className="px-10 py-3 border-b border-border text-muted-foreground text-[11px] leading-relaxed max-md:px-4" role="status">
          {services.notice}
        </p>
      )}
      {account.status === 'error' && (
        <div
          className="flex flex-wrap items-center gap-4 px-8 py-4 bg-accent text-[13px] border-b border-border [&_a]:underline [&_a]:underline-offset-4 max-md:px-4"
          role="alert"
        >
          <p>{account.error}</p>
          <Button size="sm" variant="outline" onClick={account.retry}>
            {tCommon('retry')}
          </Button>
          <Link href="/login">{tNav('signInAgain')}</Link>
        </div>
      )}
      {account.status === 'task' && (
        <div
          className="flex flex-wrap items-center gap-4 px-8 py-4 bg-accent text-[13px] border-b border-border [&_a]:underline [&_a]:underline-offset-4 max-md:px-4"
          role="status"
        >
          <p>{tNav('verificationNotice')}</p>
          <Link href="/auth/continue">{tNav('continueVerification')}</Link>
        </div>
      )}
    </>
  )
}
