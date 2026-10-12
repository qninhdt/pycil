'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'

export default function ErrorPage({ reset }: { reset: () => void }) {
  const t = useTranslations('errors')
  const tCommon = useTranslations('common')
  return <div className="px-8 py-16 flex flex-col gap-5 max-w-[680px] mx-auto [&_h1]:text-[32px] [&_h1]:font-extrabold [&_h1]:tracking-tight [&_a]:underline [&_a]:underline-offset-4" role="alert"><h1>{t('pageErrorTitle')}</h1><p>{t('pageErrorDesc')}</p><Button onClick={reset}>{tCommon('retry')}</Button><Link href="/app">{t('returnHome')}</Link></div>
}
