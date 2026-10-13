import { getTranslations } from 'next-intl/server'
import { AppShellFrame } from './app-shell-frame.client'

export async function AppShell({ children }: { children: React.ReactNode }) {
  const t = await getTranslations('nav')
  return <AppShellFrame skipToContentText={t('skipToContent')}>{children}</AppShellFrame>
}
