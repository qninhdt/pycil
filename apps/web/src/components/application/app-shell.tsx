'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { ArrowRight, Menu, Plus } from '@/components/artwork/artwork'
import { toast } from 'sonner'
import { Icon } from '@/components/artwork/artwork'
import { PatternPanel } from '@/components/artwork/pattern-panel'
import { useNavigationState } from '@/hooks/use-navigation-state'
import { useAiPanelState } from '@/hooks/use-ai-panel-state'
import { useServices } from '@/lib/services/provider'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator } from '@/components/ui/dropdown-menu'
import { Sheet, SheetTrigger, SheetContent, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { PycilBrand } from './brand'
import { DaylightArt } from './daylight-art'
import { useAccount, useTheme } from './providers'
import { mainNavigationItems as pages } from '@/lib/navigation'
import { libraryHref, publishedHref } from '@/lib/library-model'
import { PycilAI } from '@/components/assistant-ui/pycil-ai'

function AccountMenu({ mobile = false, collapsed = false }: { mobile?: boolean; collapsed?: boolean }) {
  const account = useAccount()
  const { theme, toggleTheme } = useTheme()
  const [signingOut, setSigningOut] = useState(false)
  return <DropdownMenu><DropdownMenuTrigger asChild>
    <button className={`shell-account ${mobile ? 'w-full' : 'w-[calc(100%-22px)]'} relative flex items-center p-0 overflow-hidden text-left h-[84px] transition-colors duration-150 shrink-0 focus:outline-none focus-visible:shadow-[inset_3px_0_0_var(--ring)] focus-visible:bg-accent`} aria-label="Open account menu" disabled={signingOut}>
      <Icon name="person" className="absolute left-[25.5px] size-5 shrink-0" />
      <span className={`account-copy ${collapsed ? 'hidden' : ''} absolute left-[66px] w-[147px] min-w-0 overflow-hidden whitespace-nowrap [&_strong]:block [&_strong]:text-sm [&_strong]:font-bold [&_strong]:overflow-hidden [&_strong]:text-ellipsis [&_small]:block [&_small]:text-xs [&_small]:mt-1 [&_small]:text-muted-foreground [&_small]:overflow-hidden [&_small]:text-ellipsis opacity-100 transition-opacity duration-200 motion-reduce:transition-none`}><strong>{account.status === 'loading' ? 'Loading account…' : account.name}</strong>
        <small>{account.signedIn ? `${account.profile?.plan?.toLowerCase() === 'pro' ? 'Pro' : 'Free'} plan` : 'Sign in to learn'}</small></span>
    </button>
  </DropdownMenuTrigger><DropdownMenuContent className="w-72 max-w-[calc(100vw-32px)] border-foreground" side={mobile ? 'top' : 'right'} align={mobile ? 'start' : 'end'} sideOffset={mobile ? 8 : 56} collisionPadding={16}>
    <DropdownMenuLabel>{account.signedIn ? account.name : 'Your account'}</DropdownMenuLabel>
    <DropdownMenuSeparator />
    <DropdownMenuItem asChild><Link href={account.profile ? `/u/${encodeURIComponent(account.profile.id)}` : '/app/profile'}><Icon name="person" className="size-5" />Profile</Link></DropdownMenuItem>
    <DropdownMenuItem asChild><Link href="/app/settings"><Icon name="settings" className="size-5" />Settings</Link></DropdownMenuItem>
    <DropdownMenuItem className="shell-theme-setting [&_>_[data-slot=switch]]:ml-auto" role="menuitemcheckbox" aria-label="Dark mode" aria-checked={theme === 'dark'}
      onSelect={event => { event.preventDefault(); toggleTheme() }}>
      <Icon name="dashboard" className="size-5" /><span>Dark mode</span>
      <Switch aria-label="Dark mode" tabIndex={-1} checked={theme === 'dark'} onCheckedChange={toggleTheme}
        onClick={event => event.stopPropagation()} onKeyDown={event => event.stopPropagation()} />
    </DropdownMenuItem>
    <DropdownMenuSeparator />
    {account.signedIn ? <DropdownMenuItem disabled={signingOut} onSelect={async () => {
      setSigningOut(true)
      try { await account.signOut() } catch { toast.error('Sign out did not complete. Please retry.'); setSigningOut(false) }
    }}><Icon name="sign-out" className="size-5" data-art-icon="sign-out" />{signingOut ? 'Signing out…' : 'Sign out'}</DropdownMenuItem>
      : <><DropdownMenuItem asChild><Link href="/login"><Icon name="lock" className="size-5" />Sign in</Link></DropdownMenuItem>
        <DropdownMenuItem asChild><Link href="/signup"><Icon name="group" className="size-5" />Create an account</Link></DropdownMenuItem></>}
  </DropdownMenuContent></DropdownMenu>
}

function ShellRail({ close, collapsed = false, toggleCollapsed }: { close?: () => void; collapsed?: boolean; toggleCollapsed?: () => void }) {
  const path = usePathname()
  const account = useAccount()
  const publishedOwner = path.match(/^\/app\/u\/([^/]+)\/published(?:\/|$)/)?.[1]
  const ownPublished = !!publishedOwner && !!account.profile && (publishedOwner === 'me' || publishedOwner === account.profile.id || publishedOwner === account.profile.handle)
  const isActive = (href: string) => href === '/app/personal' ? path === href || path.startsWith(`${href}/`)
    : href === '/app/u/me/published' ? !!ownPublished
    : href === '/app/discovery' ? path === href || (!!publishedOwner && !ownPublished)
    : path === href
  const [tooltip, setTooltip] = useState<string | null>(null)
  return <div className="flex h-full min-w-0 flex-col">
    <div className="shell-rail-scroll flex min-h-0 min-w-0 flex-1 flex-col overflow-x-hidden overflow-y-auto">
    <div className={`shell-brand-zone ${close ? 'px-5' : 'px-[19.5px]'} relative isolate overflow-hidden h-[88px] flex items-center gap-2 border-b border-foreground shrink-0`}><PycilBrand compact markOnly={collapsed} />
      <DaylightArt mobile={!!close} />
    </div>
    <nav aria-label="App navigation" className="shell-nav flex flex-col [&_>_a]:relative [&_>_a]:flex [&_>_a]:items-center [&_>_a]:h-14 [&_>_a]:flex-none [&_>_a]:p-0 [&_>_a]:overflow-hidden [&_>_a]:border-b [&_>_a]:border-foreground [&_>_a]:text-sm [&_>_a]:font-semibold [&_>_a]:no-underline [&_>_a]:transition-colors [&_>_a]:duration-150 [&_>_a:hover]:bg-accent [&_>_a[aria-current=page]]:bg-[var(--action-red)] [&_>_a[aria-current=page]]:text-[var(--on-action-red)] [&_>_a[aria-current=page]]:font-bold [&_>_a[aria-current=page]_.bauhaus-icon]:[--art-ink:var(--palette-canvas)] [&_>_a[aria-current=page]_.bauhaus-icon]:[--art-paper:var(--action-red)]">
      {pages.map(page => <Tooltip key={page.href} open={collapsed && tooltip === page.href} onOpenChange={open => setTooltip(current => open && collapsed ? page.href : current === page.href ? null : current)} delayDuration={250}><TooltipTrigger asChild><Link href={page.href === '/app/u/me/published' ? publishedHref(account.profile?.id ?? 'me') : page.href === '/app/personal' ? libraryHref(account.profile?.personal_node_id) : page.href} onClick={() => { setTooltip(null); close?.() }}
          aria-label={page.title} aria-current={isActive(page.href) ? 'page' : undefined}>
          <span className="absolute left-[25.5px] top-1/2 -translate-y-1/2 inline-flex items-center justify-center size-5 flex-none [&_>_.bauhaus-shape_circle]:stroke-[3]"><Icon name={page.icon} data-art-icon={page.icon} className="shell-navigation-icon size-5" tone={isActive(page.href) ? 'mono' : 'color'} /></span><span className={`shell-nav-label absolute left-[66px] max-w-[calc(100%-82px)] overflow-hidden text-ellipsis whitespace-nowrap opacity-100 transition-opacity duration-200 motion-reduce:transition-none`}>{page.title}</span>{!collapsed && isActive(page.href) && <ArrowRight className="size-[17px] ml-auto mr-[22px] flex-none" aria-hidden="true" />}
        </Link></TooltipTrigger>{collapsed && <TooltipContent side="right">{page.title}</TooltipContent>}</Tooltip>)}
    </nav>
    <div className="flex-1 min-h-10" />
    <DropdownMenu><DropdownMenuTrigger asChild>
      <button className="shell-new relative isolate overflow-hidden flex items-center w-full text-left p-0 h-[92px] border-y border-foreground transition-colors duration-150 shrink-0 [&_>_svg:first-child]:absolute [&_>_svg:first-child]:left-[25.5px] [&_>_svg:first-child]:size-5 [&_>_svg:first-child]:stroke-[1.5] [&_>_span]:absolute [&_>_span]:left-[66px] [&_>_span]:max-w-[calc(100%-82px)] [&_>_span]:overflow-hidden [&_>_span]:whitespace-nowrap [&_strong]:text-xl [&_strong]:font-extrabold [&_strong]:tracking-[-.025em] [&_small]:block [&_small]:text-xs [&_small]:mt-1 [&_small]:whitespace-nowrap hover:bg-[var(--palette-yellow-soft)] data-[state=open]:bg-[var(--palette-yellow-soft)] focus:outline-none focus-visible:shadow-[inset_3px_0_0_var(--ring)] focus-visible:bg-[var(--palette-yellow-soft)] [&_>_span]:opacity-100 [&_>_span]:transition-opacity [&_>_span]:duration-200 motion-reduce:[&_>_span]:transition-none" aria-label="New deck / folder" title={collapsed ? 'New deck / folder' : undefined}><Plus aria-hidden="true" />{!collapsed && <span><strong>New</strong><small>deck / folder</small></span>}
        {!collapsed && <svg className={`shell-new-corner ${close ? 'right-0 left-auto' : ''} absolute -z-1 size-[88px] left-[167px] bottom-0 opacity-100 transition-opacity duration-200 motion-reduce:transition-none`} viewBox="0 0 88 88" aria-hidden="true"><path d="M88 0V88H0Z" fill="var(--art-yellow)" /></svg>}
      </button>
    </DropdownMenuTrigger><DropdownMenuContent className="w-72 max-w-[calc(100vw-32px)] border-foreground" side={close ? 'top' : 'right'} align={close ? 'start' : 'end'} sideOffset={close ? 8 : 12} collisionPadding={16}>
      <DropdownMenuItem asChild><Link href="/app/personal?create=deck" onClick={close}><Icon name="collection" className="size-5" /><span>New deck</span></Link></DropdownMenuItem>
      <DropdownMenuItem asChild><Link href="/app/personal?create=folder" onClick={close}><Icon name="folder" className="size-5" /><span>New folder</span></Link></DropdownMenuItem>
    </DropdownMenuContent></DropdownMenu>
    </div>
    <div className="relative h-[84px] shrink-0 transition-colors hover:bg-accent has-[button[data-state=open]]:bg-accent">
      <AccountMenu mobile={!!close} collapsed={collapsed} />
      {toggleCollapsed && <button className="shell-collapse-handle absolute z-1 -right-[22px] top-1/2 -translate-y-1/2 flex items-center justify-center size-11 p-0 border-0 bg-transparent cursor-pointer [&_svg]:w-6 [&_svg]:h-8 [&_svg]:bg-background [&_svg]:border [&_svg]:border-foreground focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2" onClick={() => { setTooltip(null); toggleCollapsed() }}
        aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'} aria-expanded={!collapsed} aria-controls="desktop-app-navigation"
        title={collapsed ? 'Expand navigation' : 'Collapse navigation'}>
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M6 5v14" stroke="var(--art-ink)" strokeWidth="1.5" />
          {collapsed ? <path className="shell-expand-arrow" d="M11 7 18 12 11 17Z" fill="var(--art-blue)" /> : <path className="shell-expand-arrow" d="M18 7 11 12 18 17Z" fill="var(--art-blue)" />}
        </svg>
      </button>}
    </div>
  </div>
}

export function ThemeButton() {
  const { theme, toggleTheme } = useTheme()
  return <Switch aria-label="Dark mode" checked={theme === 'dark'} onCheckedChange={toggleTheme} />
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const { collapsed, toggleCollapsed } = useNavigationState()
  const account = useAccount()
  const { services } = useServices()

  return <div className="application-shell [--rail-width:256px] data-[collapsed=true]:[--rail-width:72px]" data-collapsed={collapsed}>
    <a className="skip-link" href="#app-content">Skip to content</a>
    <aside className="shell-desktop fixed inset-y-0 left-0 w-(--rail-width) z-30 border-r border-foreground bg-background transition-[width] duration-200 motion-reduce:transition-none max-md:hidden" id="desktop-app-navigation"><ShellRail collapsed={collapsed} toggleCollapsed={toggleCollapsed} /></aside>
    <div className="shell-workspace ml-(--rail-width) flex flex-col min-w-0 transition-[margin] duration-200 motion-reduce:transition-none max-md:ml-0">
      <div className="hidden max-md:flex max-md:px-4 max-md:pt-4"><Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetTrigger asChild><Button variant="ghost" size="icon" aria-label="Open navigation"><Menu /></Button></SheetTrigger>
          <SheetContent side="left" className="max-md:data-[slot=sheet-content]:w-[min(300px,calc(100vw-32px))] max-md:data-[slot=sheet-content]:gap-0 max-md:data-[slot=sheet-content]:p-0 max-md:data-[slot=sheet-content]:bg-background !border-foreground">
            <SheetTitle className="sr-only">Pycil navigation</SheetTitle><SheetDescription className="sr-only">Navigate your workspace and manage your account.</SheetDescription>
            <ShellRail close={() => setMobileOpen(false)} />
          </SheetContent>
        </Sheet></div>
      {services.notice && <p className="px-10 py-3 border-b border-border text-muted-foreground text-[11px] leading-relaxed max-md:px-6" role="status">{services.notice}</p>}
      {account.status === 'error' && <div className="flex flex-wrap items-center gap-4 px-8 py-4 bg-accent text-[13px] border-b border-border [&_a]:underline [&_a]:underline-offset-4 max-md:px-6" role="alert"><p>{account.error}</p><Button size="sm" variant="outline" onClick={account.retry}>Retry</Button><Link href="/login">Sign in again</Link></div>}
      {account.status === 'task' && <div className="flex flex-wrap items-center gap-4 px-8 py-4 bg-accent text-[13px] border-b border-border [&_a]:underline [&_a]:underline-offset-4 max-md:px-6" role="status"><p>Your account needs an additional verification step.</p><Link href="/auth/continue">Continue verification</Link></div>}
      <main id="app-content" className="flex flex-col flex-1 min-w-0" tabIndex={-1}>
        <div className="mx-auto w-full max-w-[1520px] min-w-0 flex-1 px-5 py-8 sm:px-8 lg:px-10 lg:py-12">{children}</div>
        <PatternPanel className="shell-main-pattern" seed="pycil-1923" />
      </main>
    </div>
    <PycilAI />
  </div>
}
