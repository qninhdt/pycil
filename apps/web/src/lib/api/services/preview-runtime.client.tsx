'use client'

import { useState } from 'react'
import { NextIntlClientProvider, type AbstractIntlMessages } from 'next-intl'
import { IdentityContext } from '@/features/account/account.client'
import { defaultLocale, type Locale } from '@/lib/preferences/locale'
import { createMockServices } from './mock'
import { ServicesProvider } from './provider.client'

let browserServices: ReturnType<typeof createMockServices> | undefined
function previewServices() {
  if (typeof window === 'undefined') return createMockServices()
  return browserServices ??= createMockServices()
}

export function PreviewRuntime({ children, locale = defaultLocale, messages }: { children: React.ReactNode; locale?: Locale; messages: AbstractIntlMessages }) {
  const [services] = useState(previewServices)
  const [signedOut, setSignedOut] = useState(false)
  const scope = signedOut ? 'signed-out' : services.account.initialProfile!.id
  return <NextIntlClientProvider locale={locale} messages={messages}>
    <ServicesProvider services={services} scope={scope}>
      <IdentityContext.Provider value={{ state: signedOut ? 'signed-out' : 'authenticated', initialProfile: services.account.initialProfile, signOut: async () => setSignedOut(true) }}>{children}</IdentityContext.Provider>
    </ServicesProvider>
  </NextIntlClientProvider>
}
