'use client'

import Link from 'next/link'
import { useState } from 'react'
import { toast } from 'sonner'
import { Icon } from '@/components/artwork/artwork'
import { Switch } from '@/components/ui/switch'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu'
import { useAccount } from '@/features/account/account.client'
import { useTheme } from '@/lib/preferences/theme-provider.client'
import { useTranslations } from 'next-intl'

export function AccountMenu({
  mobile = false,
  collapsed = false,
  close,
}: {
  mobile?: boolean
  collapsed?: boolean
  close?: () => void
}) {
  const account = useAccount()
  const { theme, toggleTheme } = useTheme()
  const tNav = useTranslations('nav')
  const [signingOut, setSigningOut] = useState(false)

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className={`shell-account ${mobile ? 'w-full' : 'w-[calc(100%-22px)]'} relative flex items-center p-0 overflow-hidden text-left h-[84px] transition-colors duration-150 shrink-0 focus:outline-none focus-visible:shadow-[inset_3px_0_0_var(--ring)] focus-visible:bg-accent`}
          aria-label={tNav('openAccountMenu')}
          disabled={signingOut}
        >
          <Icon name="person" className="absolute left-[25.5px] size-5 shrink-0" />
          <span
            className={`account-copy ${collapsed ? 'hidden' : ''} absolute left-[66px] w-[147px] min-w-0 overflow-hidden whitespace-nowrap [&_strong]:block [&_strong]:text-sm [&_strong]:font-bold [&_strong]:overflow-hidden [&_strong]:text-ellipsis [&_small]:block [&_small]:text-xs [&_small]:mt-1 [&_small]:text-muted-foreground [&_small]:overflow-hidden [&_small]:text-ellipsis opacity-100 transition-opacity duration-200 motion-reduce:transition-none`}
          >
            <strong>{account.status === 'loading' ? tNav('loadingAccount') : account.name}</strong>
            <small>
              {account.signedIn
                ? `${account.profile?.plan?.toLowerCase() === 'pro' ? tNav('proPlan') : tNav('freePlan')}`
                : tNav('signInToLearn')}
            </small>
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        className="w-72 max-w-[calc(100vw-32px)] border-foreground"
        side={mobile ? 'top' : 'right'}
        align={mobile ? 'start' : 'end'}
        sideOffset={mobile ? 8 : 56}
        collisionPadding={16}
      >
        <DropdownMenuLabel>{account.signedIn ? account.name : tNav('yourAccount')}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {account.signedIn && <><DropdownMenuItem asChild>
          <Link href={account.profile ? `/u/${encodeURIComponent(account.profile.id)}` : '/login'} onClick={close}>
            <Icon name="person" className="size-5" />
            {tNav('profile')}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/app/settings" onClick={close}>
            <Icon name="settings" className="size-5" />
            {tNav('settings')}
          </Link>
        </DropdownMenuItem></>}
        <DropdownMenuItem
          className="shell-theme-setting [&_>_[data-slot=switch]]:ml-auto"
          role="menuitemcheckbox"
          aria-label={tNav('darkMode')}
          aria-checked={theme === 'dark'}
          onSelect={event => {
            event.preventDefault()
            toggleTheme()
          }}
        >
          <Icon name="dashboard" className="size-5" />
          <span>{tNav('darkMode')}</span>
          <Switch
            aria-label={tNav('darkMode')}
            tabIndex={-1}
            checked={theme === 'dark'}
            onCheckedChange={toggleTheme}
            onClick={event => event.stopPropagation()}
            onKeyDown={event => event.stopPropagation()}
          />
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        {account.signedIn ? (
          <DropdownMenuItem
            disabled={signingOut}
            onSelect={async () => {
              setSigningOut(true)
              try {
                await account.signOut()
              } catch {
                toast.error('Sign out did not complete. Please retry.')
                setSigningOut(false)
              }
            }}
          >
            <Icon name="sign-out" className="size-5" data-art-icon="sign-out" />
            {signingOut ? tNav('signingOut') : tNav('signOut')}
          </DropdownMenuItem>
        ) : (
          <>
            <DropdownMenuItem asChild>
              <Link href="/login" onClick={close}>
                <Icon name="lock" className="size-5" />
                {tNav('signIn')}
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/signup" onClick={close}>
                <Icon name="group" className="size-5" />
                {tNav('createAccount')}
              </Link>
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

