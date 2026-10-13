import { AppShell } from '@/components/shell/app-shell'

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>
}
