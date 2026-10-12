'use client'
import { useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { useAccount } from '@/components/application/providers'
import { Button } from '@/components/ui/button'

export function ProfileRedirect() {
  const account = useAccount(), router = useRouter()
  const t = useTranslations('account')
  const tNav = useTranslations('nav')
  const tCommon = useTranslations('common')
  useEffect(() => { if (account.profile) router.replace(`/u/${encodeURIComponent(account.profile.id)}`) }, [account.profile, router])
  return <div className="w-full py-8 [&_h1]:text-[clamp(2.25rem,2.6vw,3rem)] [&_h1]:font-extrabold [&_h1]:leading-[1.12] [&_h1]:tracking-[-.03em] [&_p]:mt-3 [&_p]:mb-5.5 [&_p]:text-muted-foreground"><h1>{tNav('profile')}</h1>{account.status === 'signed-out' ? <p>{t('signInToViewProfile')} <Link href="/login" className="underline underline-offset-4">{tCommon('signIn')}</Link></p>
    : account.status === 'error' ? <><p>{account.error || t('couldNotLoadAccount')}</p><Button variant="outline" onClick={account.retry}>{tCommon('retry')}</Button></>
      : account.status === 'task' ? <p>{t.rich('completeVerificationToOpenProfile', { link: (chunks) => <Link href="/auth/continue" className="underline underline-offset-4">{chunks}</Link> })}</p>
        : <p>{t('openingPublicProfile')}</p>}</div>
}
