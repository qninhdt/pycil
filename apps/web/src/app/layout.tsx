import type { Metadata } from 'next'
import { Providers } from '@/components/application/providers'
import { initialUiScript } from '@/lib/ui-preferences'
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

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en" data-scroll-behavior="smooth" data-time-of-day="morning" data-navigation-collapsed="false" suppressHydrationWarning>
    <head>
      <link id="app-icon" rel="icon" href="/favicon.svg" type="image/svg+xml" />
      <link rel="alternate icon" href="/favicon.ico" />
      <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
      <script dangerouslySetInnerHTML={{ __html: initialUiScript }} />
    </head>
    <body><Providers>{children}</Providers></body>
  </html>
}
