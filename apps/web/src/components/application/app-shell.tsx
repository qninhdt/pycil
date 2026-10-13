'use client'

import { useTranslations } from 'next-intl'
import { AppShellFrame } from './app-shell-frame'

export { ThemeButton } from './account-menu'

export function AppShell({ children }: { children: React.ReactNode }) {
  const tNav = useTranslations('nav')
  return (
    <AppShellFrame skipToContentText={tNav('skipToContent')}>
      {children}
    </AppShellFrame>
  )
}
