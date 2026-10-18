'use client'

import Link from 'next/link'
import { useAuth, UserButton } from '@clerk/nextjs'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import { ArrowUpRight } from '@/components/artwork/artwork'
import { authConfigured } from '@/lib/auth/config'

function GuestLinks() {
  const t = useTranslations('landing')
  return <><Link href="/login">{t('signIn')}</Link><Button asChild><Link href="/signup">{t('getStarted')}<ArrowUpRight /></Link></Button></>
}

function ClerkAccount() {
  const { isLoaded, isSignedIn } = useAuth()
  const t = useTranslations('landing')
  if (!isLoaded) return <span className="inline-block h-10 w-40" aria-busy="true" />
  if (!isSignedIn) return <GuestLinks />
  return <><Button asChild><Link href="/app">{t('openApp')}<ArrowUpRight /></Link></Button><UserButton /></>
}

export function LandingAccount() {
  return authConfigured ? <ClerkAccount /> : <GuestLinks />
}
