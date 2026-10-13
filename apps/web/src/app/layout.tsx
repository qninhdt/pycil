import type { Metadata } from 'next'
import { ClerkProvider } from '@clerk/nextjs'
import { getLocale, getMessages } from 'next-intl/server'
import { NextIntlClientProvider } from 'next-intl'
import { cookies } from 'next/headers'
import { ThemeProvider } from '@/lib/preferences/theme-provider.client'
import { resolveTheme, themeCookie } from '@/lib/preferences/theme'
import { UiProvider } from '@/lib/preferences/ui-provider.client'
import { dataMode } from '@/lib/api/services/config'
import { initialUiScript } from '@/lib/preferences/browser'
import './globals.css'


export const metadata: Metadata = {
  title: { default: 'Pycil', template: '%s — Pycil' },
  description: 'Organize the meanings you want to learn. Practice, review, and return at your own pace.',
  icons: {
    icon: [
      { url: '/favicon.svg', type: 'image/svg+xml' },
      { url: '/favicon.ico', sizes: '32x32' },
    ],
    apple: '/apple-touch-icon.png',
  },
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const [initialLocale, messages, cookieStore] = await Promise.all([getLocale(), getMessages(), cookies()])
  const theme = resolveTheme(cookieStore.get(themeCookie)?.value)
  const contents = <NextIntlClientProvider locale={initialLocale} messages={messages}>
    <ThemeProvider initialTheme={theme}><UiProvider>{children}</UiProvider></ThemeProvider>
  </NextIntlClientProvider>
  const authenticated = dataMode === 'live' && process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
    ? <ClerkProvider dynamic prefetchUI={false} signInUrl="/login" signUpUrl="/signup" signInFallbackRedirectUrl="/app" signUpFallbackRedirectUrl="/app" afterSignOutUrl="/login">{contents}</ClerkProvider>
    : contents
  return <html className={theme === 'dark' ? 'dark' : undefined} lang={initialLocale} data-scroll-behavior="smooth" data-time-of-day="morning" data-navigation-collapsed="false" suppressHydrationWarning>
    <head>
      <link id="app-icon" rel="icon" href="/favicon.svg" type="image/svg+xml" />
      <link rel="alternate icon" href="/favicon.ico" />
      <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
      <script dangerouslySetInnerHTML={{ __html: initialUiScript }} />
    </head>
    <body>{authenticated}</body>
  </html>
}
