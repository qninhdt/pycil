'use client'

import { AssistantViewProvider } from '@/features/assistant/current-view.client'
import { useWorkspaceScroll } from '@/components/shell/use-workspace-scroll.client'
import { useNavigationState } from '@/components/shell/use-navigation-state.client'
import { ShellRail } from './shell-rail.client'
import { MobileAppBar } from './mobile-app-bar.client'
import { AppShellStatus } from './app-shell-status.client'
import { PatternPanel } from '@/components/artwork/pattern-panel'
import { PycilAI } from '@/features/assistant/pycil-ai.client'
import { useAccount } from '@/features/account/account.client'

export function AppShellFrame({
  children,
  skipToContentText,
}: {
  children: React.ReactNode
  skipToContentText: string
}) {
  const workspace = useWorkspaceScroll()
  const account = useAccount()
  const { collapsed, toggleCollapsed } = useNavigationState()

  return (
    <AssistantViewProvider><div
      className="application-shell [--rail-width:256px] data-[collapsed=true]:[--rail-width:72px]"
      data-collapsed={collapsed}
    >
      <a className="skip-link" href="#app-content">
        {skipToContentText}
      </a>
      <aside
        className="shell-desktop fixed inset-y-0 left-0 w-(--rail-width) z-30 border-r border-foreground bg-background transition-[width] duration-200 motion-reduce:transition-none max-md:hidden"
        id="desktop-app-navigation"
      >
        <ShellRail collapsed={collapsed} toggleCollapsed={toggleCollapsed} />
      </aside>
      <div
        ref={workspace}
        className="shell-workspace ml-(--rail-width) flex flex-col min-w-0 transition-[margin] duration-200 motion-reduce:transition-none max-md:ml-0"
      >
        <MobileAppBar />
        <AppShellStatus />
        <main id="app-content" className="flex flex-col flex-1 min-w-0" tabIndex={-1}>
          <div className="mx-auto w-full max-w-[1520px] min-w-0 flex-1 px-4 py-5 sm:px-8 sm:py-8 lg:px-10 lg:py-12">
            {children}
          </div>
          <PatternPanel className="shell-main-pattern" seed="pycil-1923" />
        </main>
      </div>
      {account.status === 'ready' && <PycilAI />}
    </div></AssistantViewProvider>
  )
}
