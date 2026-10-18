'use client'

import { useRef, useState } from 'react'
import { Menu, Icon } from '@/components/artwork/artwork'
import { Sheet, SheetTrigger, SheetContent, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { PycilBrand } from './brand'
import { ShellRail } from './shell-rail.client'
import { useAiPanelState } from '@/features/assistant/use-panel-state.client'
import { useAccount } from '@/features/account/account.client'
import { useTranslations } from 'next-intl'

export function MobileAppBar() {
  const trigger = useRef<HTMLButtonElement>(null)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { setOpen: setAiOpen } = useAiPanelState()
  const account = useAccount()
  const tNav = useTranslations('nav')

  return (
    <header className="hidden max-md:grid grid-cols-[56px_1fr_56px] sticky top-0 z-30 h-14 w-full items-center border-b border-foreground bg-background/95 backdrop-blur-sm shrink-0">
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetTrigger asChild>
          <button
            ref={trigger}
            type="button"
            className="grid place-items-center h-full w-14 border-r border-foreground hover:bg-accent text-foreground transition-colors cursor-pointer"
            aria-label={tNav('openNav')}
          >
            <Menu className="size-5" />
          </button>
        </SheetTrigger>
        <SheetContent
          onCloseAutoFocus={event => { event.preventDefault(); trigger.current?.focus({ preventScroll: true }) }}
          side="left"
          showCloseButton={false}
          className="max-md:data-[slot=sheet-content]:w-[min(300px,calc(100vw-32px))] max-md:data-[slot=sheet-content]:gap-0 max-md:data-[slot=sheet-content]:p-0 max-md:data-[slot=sheet-content]:bg-background !border-foreground"
        >
          <SheetTitle className="sr-only">{tNav('pycilNav')}</SheetTitle>
          <SheetDescription className="sr-only">{tNav('navWorkspaceDesc')}</SheetDescription>
          <ShellRail close={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>
      <div className="flex items-center justify-center h-full px-2 min-w-0">
        <PycilBrand compact />
      </div>
      {account.status === 'ready' && <button
        type="button"
        onClick={() => setAiOpen(true)}
        className="grid place-items-center h-full w-14 border-l border-foreground hover:bg-accent text-foreground transition-colors cursor-pointer"
        aria-label="PycilAI"
        title="PycilAI"
      >
        <Icon name="spark" tone="color" className="size-5" />
      </button>}
    </header>
  )
}
