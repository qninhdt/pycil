import { AppShell } from '@/components/application/app-shell'

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>
}
