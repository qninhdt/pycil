'use client'

import Link from 'next/link'
import dynamic from 'next/dynamic'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Icon } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { cn } from 'cn'
import { toast } from 'sonner'
import { useAiPanelState } from '@/hooks/use-ai-panel-state'
import { useServices } from '@/lib/services/provider'
import { useAccount } from '@/components/application/providers'
import { AssistantGeometry } from './thread'

export { ApprovalPanel } from './live-assistant'

const LiveAssistant = dynamic(
  () => import('./live-assistant').then(mod => mod.LiveAssistant),
  {
    ssr: false,
    loading: () => (
      <div className="ai-state">
        <AssistantGeometry />
        <p>Loading AI Assistant…</p>
      </div>
    ),
  }
)

function AiSettingsDropdown({ disabled }: { disabled?: boolean }) {
  const t = useTranslations('assistant')
  const tAccount = useTranslations('account')
  const { services, scope } = useServices()
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)
  const profile = useQuery({
    queryKey: [services.mode, scope, 'account'],
    queryFn: ({ signal }) => services.account.profile(signal),
    enabled: !disabled,
  })

  const usage = useQuery({
    queryKey: [services.mode, scope, 'usage'],
    queryFn: ({ signal }) => services.account.usage(signal),
    enabled: !!services.account,
  })

  const handleToggleAutoApprove = async (checked: boolean) => {
    setSaving(true)
    try {
      const next = await services.account.updateSettings(
        { assistant: { auto_approve: checked } },
        new AbortController().signal
      )
      queryClient.setQueryData([services.mode, scope, 'account'], next)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : tAccount('couldNotSaveSettings'))
    } finally {
      setSaving(false)
    }
  }

  const allowance = usage.data?.allowance_units ?? 1
  const remaining = usage.data?.remaining_units ?? 0
  const used = Math.max(0, allowance - remaining)
  const ratio = allowance > 0 ? Math.min(1, Math.max(0, used / allowance)) : 0
  const percent = Math.round(ratio * 100)

  const isExhausted = usage.data ? remaining <= 0 : false
  const isNearLimit = usage.data ? ratio >= 0.8 : false

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={t('aiSettings')}
          title={t('aiSettings')}
          disabled={disabled}
        >
          <Icon name="more" variant="control" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={6}
        className="w-72 p-3.5 space-y-3.5 border-border bg-popover text-popover-foreground shadow-none rounded-none"
      >
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-bold tracking-tight">
            <span className="text-[11px] font-bold uppercase tracking-[.08em] text-muted-foreground">
              {t('aiUnitUsage')}
            </span>
            {isExhausted ? (
              <span className="px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider border border-art-red bg-art-red/10 text-art-red">
                {t('quotaExhausted')}
              </span>
            ) : isNearLimit ? (
              <span className="px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider border border-art-yellow bg-art-yellow/20 text-[var(--palette-sunflower-dark,#b7950b)]">
                {t('quotaNearLimit')}
              </span>
            ) : null}
          </div>

          <div
            className="h-2 w-full bg-muted border border-border overflow-hidden relative"
            role="progressbar"
            aria-label={t('aiUnitUsage')}
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className={cn(
                'h-full transition-all duration-300 ease-out',
                isExhausted ? 'bg-art-red' : isNearLimit ? 'bg-art-yellow' : 'bg-art-blue'
              )}
              style={{ width: `${percent}%` }}
            />
          </div>

          {usage.data?.period_end && (
            <p className="text-[11px] text-muted-foreground">
              {t('resetsDate', {
                date: new Date(usage.data.period_end).toLocaleDateString(undefined, {
                  month: 'short',
                  day: 'numeric',
                }),
              })}
            </p>
          )}
        </div>

        <div className="h-px bg-border -mx-3.5" />

        <div className="flex items-center justify-between gap-3 pt-0.5">
          <Label
            htmlFor="ai-auto-approve-toggle"
            className="text-xs font-bold leading-none cursor-pointer block select-none"
          >
            {t('bypassPermissionTitle')}
          </Label>
          <Switch
            id="ai-auto-approve-toggle"
            size="sm"
            checked={profile.data?.settings.assistant.auto_approve ?? false}
            disabled={saving || !profile.data || disabled}
            onCheckedChange={checked => {
              void handleToggleAutoApprove(checked)
            }}
            aria-label={t('bypassPermissionTitle')}
          />
        </div>
        {profile.isError && <p className="text-xs text-destructive" role="alert">{profile.error.message}</p>}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function PycilAI() {
  const { scope } = useServices()
  return <PycilAIPanel key={scope} />
}

function PycilAIPanel() {
  const { services, scope } = useServices()
  const account = useAccount()
  const t = useTranslations('assistant')
  const tCommon = useTranslations('common')
  const { open, setOpen } = useAiPanelState()
  const [historyOpen, setHistoryOpen] = useState(false)
  const [newKey, setNewKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [lastId, setLastId] = useState<string | null>(() => {
    try {
      return typeof window === 'undefined' ? null : localStorage.getItem(`pycil:assistant:${scope}`)
    } catch {
      return null
    }
  })
  function remember(id: string | null) {
    setLastId(id)
    try {
      if (id) localStorage.setItem(`pycil:assistant:${scope}`, id)
      else localStorage.removeItem(`pycil:assistant:${scope}`)
    } catch {
      /* Server history remains available when browser storage is blocked. */
    }
  }
  const [activeTitle, setActiveTitle] = useState<string | null>(null)
  const [width, setWidth] = useState(() => {
    if (typeof window === 'undefined') return 460
    try {
      const saved = localStorage.getItem('pycil-ai-panel-width')
      const parsed = saved ? parseInt(saved, 10) : 460
      return isNaN(parsed) ? 460 : Math.max(340, Math.min(parsed, 920))
    } catch {
      return 460
    }
  })
  const [isResizing, setIsResizing] = useState(false)
  const launcherRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    document.documentElement.style.setProperty('--ai-panel-width', `${width}px`)
  }, [width])

  const handlePointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault()
      setIsResizing(true)
      const startX = e.clientX
      const startWidth = width

      const onPointerMove = (moveEvent: PointerEvent) => {
        const deltaX = startX - moveEvent.clientX
        const maxW = Math.min(920, window.innerWidth - 60)
        const nextWidth = Math.max(340, Math.min(startWidth + deltaX, maxW))
        setWidth(nextWidth)
        try {
          localStorage.setItem('pycil-ai-panel-width', String(nextWidth))
        } catch {}
        document.documentElement.style.setProperty('--ai-panel-width', `${nextWidth}px`)
      }

      const onPointerUp = () => {
        setIsResizing(false)
        window.removeEventListener('pointermove', onPointerMove)
        window.removeEventListener('pointerup', onPointerUp)
      }

      window.addEventListener('pointermove', onPointerMove)
      window.addEventListener('pointerup', onPointerUp)
    },
    [width]
  )

  const handleDoubleClick = useCallback(() => {
    setWidth(460)
    try {
      localStorage.setItem('pycil-ai-panel-width', '460')
    } catch {}
    document.documentElement.style.setProperty('--ai-panel-width', '460px')
  }, [])

  const handleClose = useCallback(() => {
    setOpen(false)
    setTimeout(() => {
      launcherRef.current?.focus()
    }, 0)
  }, [setOpen])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      const hasOpenOverlay = !!document.querySelector(
        '[data-radix-popper-content-wrapper], [role="menu"], [role="listbox"]'
      )
      if (hasOpenOverlay) return
      event.preventDefault()
      handleClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, handleClose])

  return (
    <>
      <button
        ref={launcherRef}
        className="ai-launcher"
        data-open={open}
        aria-label={t('openPycilAI')}
        title="PycilAI"
        disabled={account.status === 'loading'}
        onClick={() => setOpen(true)}
      >
        <Icon name="spark" tone="color" className="size-6 shrink-0" />
      </button>
      {open && (
        <aside className="ai-panel" aria-label="PycilAI">
          <div
            className="ai-resize-handle"
            role="separator"
            aria-orientation="vertical"
            aria-label={t('resizePanel')}
            data-resizing={isResizing}
            onPointerDown={handlePointerDown}
            onDoubleClick={handleDoubleClick}
            title={t('resizePanelTitle')}
          />
          <header className="ai-header">
            <div className="ai-header-left">
              <button
                type="button"
                className="ai-chat-selector"
                onClick={() => setHistoryOpen(value => !value)}
                disabled={busy || !services.assistant || !account.signedIn}
                aria-label={t('conversationSelector')}
                title={activeTitle || t('newAIChat')}
              >
                <span className="ai-chat-selector-title">
                  {historyOpen ? t('conversations') : activeTitle || t('newAIChat')}
                </span>
                <Icon name="chevron-down" variant="control" className="size-3 shrink-0 text-muted-foreground" />
              </button>
            </div>
            <div className="ai-header-actions">
              <Button
                variant="ghost"
                size="icon"
                aria-label={t('newConversation')}
                title={t('newConversation')}
                disabled={busy || !services.assistant || !account.signedIn}
                onClick={() => {
                  remember(null)
                  setActiveTitle(null)
                  setNewKey(value => value + 1)
                  setHistoryOpen(false)
                }}
              >
                <Icon name="plus" variant="control" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                aria-label={t('conversationHistory')}
                title={t('conversationHistory')}
                disabled={busy || !services.assistant || !account.signedIn}
                onClick={() => setHistoryOpen(value => !value)}
              >
                <Icon name="history" />
              </Button>
              <AiSettingsDropdown disabled={busy || !services.assistant || !account.signedIn} />
              <Button variant="ghost" size="icon" aria-label={t('closePycilAI')} title={t('closePanel')} onClick={handleClose}>
                <Icon name="x" variant="control" />
              </Button>
            </div>
          </header>
          <div className="ai-panel-body">
            {!services.assistant ? (
              <div className="ai-state">
                <AssistantGeometry />
                <h3>{t('meetPycilAi')}</h3>
                <p>{t('meetPycilAiDesc')}</p>
                <Button variant="outline" asChild>
                  <Link href="/showcase?view=assistant">{t('openAssistantShowcase')}</Link>
                </Button>
              </div>
            ) : !account.signedIn ? (
              <div className="ai-state">
                <AssistantGeometry />
                <h3>{t('placeForQuestions')}</h3>
                <p>{t('placeForQuestionsDesc')}</p>
                <Button asChild>
                  <Link href="/login">{tCommon('signIn')}</Link>
                </Button>
              </div>
            ) : (
              <LiveAssistant
                key={`${scope}:${newKey}`}
                initialId={lastId}
                remember={remember}
                historyOpen={historyOpen}
                closeHistory={() => setHistoryOpen(false)}
                busy={busy}
                setBusy={setBusy}
                onTitleChange={setActiveTitle}
              />
            )}
          </div>
        </aside>
      )}
    </>
  )
}
