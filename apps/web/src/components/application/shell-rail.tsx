'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import { Plus, X, Icon } from '@/components/artwork/artwork'
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { PycilBrand } from './brand'
import { DaylightArt } from './daylight-art'
import { AccountMenu } from './account-menu'
import { useAccount } from '@/components/application/providers'
import { useTranslations } from 'next-intl'
import { mainNavigationItems as pages } from '@/lib/navigation'
import { libraryHref, publishedHref } from '@/lib/library-model'

export function ShellRail({
  close,
  collapsed = false,
  toggleCollapsed,
}: {
  close?: () => void
  collapsed?: boolean
  toggleCollapsed?: () => void
}) {
  const path = usePathname() ?? ''
  const account = useAccount()
  const tNav = useTranslations('nav')
  const tCommon = useTranslations('common')
  const publishedOwner = path.match(/^\/app\/u\/([^/]+)\/published(?:\/|$)/)?.[1]
  const ownPublished =
    !!publishedOwner &&
    !!account.profile &&
    (publishedOwner === 'me' || publishedOwner === account.profile.id || publishedOwner === account.profile.handle)
  const isActive = (href: string) =>
    href === '/app/personal'
      ? path === href || path.startsWith(`${href}/`)
      : href === '/app/u/me/published'
        ? !!ownPublished
        : href === '/app/discovery'
          ? path === href || (!!publishedOwner && !ownPublished)
          : path === href
  const [tooltip, setTooltip] = useState<string | null>(null)

  return (
    <div className="flex h-full min-w-0 flex-col">
      <div className="shell-rail-scroll flex min-h-0 min-w-0 flex-1 flex-col overflow-x-hidden overflow-y-auto">
        <div
          className={`shell-brand-zone ${close ? 'px-4' : 'px-[19.5px]'} relative isolate overflow-hidden h-[72px] sm:h-[88px] flex items-center justify-between border-b border-foreground shrink-0`}
        >
          <PycilBrand compact markOnly={collapsed} />
          <DaylightArt mobile={!!close} />
          {close && (
            <button
              type="button"
              onClick={close}
              className="grid place-items-center size-9 border border-foreground hover:bg-accent text-foreground transition-colors cursor-pointer rounded-none"
              aria-label={tCommon('close')}
            >
              <X className="size-4" />
            </button>
          )}
        </div>
        <nav
          aria-label={tNav('appNav')}
          className="shell-nav flex flex-col [&_>_a]:relative [&_>_a]:flex [&_>_a]:items-center [&_>_a]:h-14 [&_>_a]:flex-none [&_>_a]:p-0 [&_>_a]:overflow-hidden [&_>_a]:border-b [&_>_a]:border-foreground [&_>_a]:text-sm [&_>_a]:font-semibold [&_>_a]:no-underline [&_>_a]:transition-colors [&_>_a]:duration-150 [&_>_a:hover]:bg-accent [&_>_a[aria-current=page]]:bg-accent [&_>_a[aria-current=page]]:text-foreground [&_>_a[aria-current=page]]:font-bold [&_>_a[aria-current=page]]:border-l-4 [&_>_a[aria-current=page]]:border-l-art-red"
        >
          {pages.map(page => {
            const title = tNav(page.key)
            return (
              <Tooltip
                key={page.href}
                open={collapsed && tooltip === page.href}
                onOpenChange={open => setTooltip(current => (open && collapsed ? page.href : current === page.href ? null : current))}
                delayDuration={250}
              >
                <TooltipTrigger asChild>
                  <Link
                    href={
                      page.href === '/app/u/me/published'
                        ? publishedHref(account.profile?.id ?? 'me')
                        : page.href === '/app/personal'
                          ? libraryHref(account.profile?.personal_node_id)
                          : page.href
                    }
                    onClick={() => {
                      setTooltip(null)
                      close?.()
                    }}
                    aria-label={title}
                    aria-current={isActive(page.href) ? 'page' : undefined}
                  >
                    <span className="absolute left-[25.5px] top-1/2 -translate-y-1/2 inline-flex items-center justify-center size-5 flex-none [&_>_.bauhaus-shape_circle]:stroke-[3]">
                      <Icon
                        name={page.icon}
                        data-art-icon={page.icon}
                        className="shell-navigation-icon size-5"
                        tone={isActive(page.href) ? 'mono' : 'color'}
                      />
                    </span>
                    <span className="shell-nav-label absolute left-[66px] max-w-[calc(100%-82px)] overflow-hidden text-ellipsis whitespace-nowrap opacity-100 transition-opacity duration-200 motion-reduce:transition-none">
                      {title}
                    </span>
                  </Link>
                </TooltipTrigger>
                {collapsed && <TooltipContent side="right">{title}</TooltipContent>}
              </Tooltip>
            )
          })}
        </nav>
        <div className="flex-1 min-h-10" />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className="shell-new relative isolate overflow-hidden flex items-center w-full text-left p-0 h-[92px] border-y border-foreground transition-colors duration-150 shrink-0 [&_>_svg:first-child]:absolute [&_>_svg:first-child]:left-[25.5px] [&_>_svg:first-child]:size-5 [&_>_svg:first-child]:stroke-[1.5] [&_>_span]:absolute [&_>_span]:left-[66px] [&_>_span]:max-w-[calc(100%-82px)] [&_>_span]:overflow-hidden [&_>_span]:whitespace-nowrap [&_strong]:text-xl [&_strong]:font-extrabold [&_strong]:tracking-[-.025em] [&_small]:block [&_small]:text-xs [&_small]:mt-1 [&_small]:whitespace-nowrap hover:bg-[var(--palette-yellow-soft)] data-[state=open]:bg-[var(--palette-yellow-soft)] focus:outline-none focus-visible:shadow-[inset_3px_0_0_var(--ring)] focus-visible:bg-[var(--palette-yellow-soft)] [&_>_span]:opacity-100 [&_>_span]:transition-opacity [&_>_span]:duration-200 motion-reduce:[&_>_span]:transition-none"
              aria-label={tNav('newDeckOrFolder')}
              title={collapsed ? tNav('newDeckOrFolder') : undefined}
            >
              <Plus aria-hidden="true" />
              {!collapsed && (
                <span>
                  <strong>{tNav('new')}</strong>
                  <small>{tNav('newDeckOrFolder')}</small>
                </span>
              )}
              {!collapsed && !close && (
                <svg
                  className="shell-new-corner absolute -z-1 size-[88px] left-[167px] bottom-0 opacity-100 transition-opacity duration-200 motion-reduce:transition-none"
                  viewBox="0 0 88 88"
                  aria-hidden="true"
                >
                  <path d="M88 0V88H0Z" fill="var(--art-yellow)" />
                </svg>
              )}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-72 max-w-[calc(100vw-32px)] border-foreground"
            side={close ? 'top' : 'right'}
            align={close ? 'start' : 'end'}
            sideOffset={close ? 8 : 12}
            collisionPadding={16}
          >
            <DropdownMenuItem asChild>
              <Link href="/app/personal?create=deck" onClick={close}>
                <Icon name="collection" className="size-5" />
                <span>{tNav('newDeck')}</span>
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/app/personal?create=folder" onClick={close}>
                <Icon name="folder" className="size-5" />
                <span>{tNav('newFolder')}</span>
              </Link>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="relative h-[84px] shrink-0 transition-colors hover:bg-accent has-[button[data-state=open]]:bg-accent">
        <AccountMenu mobile={!!close} collapsed={collapsed} close={close} />
        {toggleCollapsed && (
          <button
            className="shell-collapse-handle absolute z-1 -right-[22px] top-1/2 -translate-y-1/2 flex items-center justify-center size-11 p-0 border-0 bg-transparent cursor-pointer [&_svg]:w-6 [&_svg]:h-8 [&_svg]:bg-background [&_svg]:border [&_svg]:border-foreground focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
            onClick={() => {
              setTooltip(null)
              toggleCollapsed()
            }}
            aria-label={collapsed ? tNav('expandNav') : tNav('collapseNav')}
            aria-expanded={!collapsed}
            aria-controls="desktop-app-navigation"
            title={collapsed ? tNav('expandNav') : tNav('collapseNav')}
          >
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M6 5v14" stroke="var(--art-ink)" strokeWidth="1.5" />
              {collapsed ? (
                <path className="shell-expand-arrow" d="M11 7 18 12 11 17Z" fill="var(--art-blue)" />
              ) : (
                <path className="shell-expand-arrow" d="M18 7 11 12 18 17Z" fill="var(--art-blue)" />
              )}
            </svg>
          </button>
        )}
      </div>
    </div>
  )
}
