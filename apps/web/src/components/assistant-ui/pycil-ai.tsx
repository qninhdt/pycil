'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { HttpAgent } from '@ag-ui/client'
import { RunAgentInputSchema } from '@ag-ui/core'
import { AssistantRuntimeProvider, ExportedMessageRepository, SimpleImageAttachmentAdapter, useAuiState, type AttachmentAdapter } from '@assistant-ui/react'
import { fromAgUiMessages, useAgUiRuntime, useAgUiInterrupts, useAgUiSubmitInterruptResponses } from '@assistant-ui/react-ag-ui'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { Icon } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel } from '@/components/ui/alert-dialog'
import { useAiPanelState } from '@/hooks/use-ai-panel-state'
import { useServices } from '@/lib/services/provider'
import { useAccount } from '@/components/application/providers'
import { AssistantThread, AssistantGeometry } from './thread'
import { UsageStatus } from '@/components/account/usage-status'
import { turnInput, type Approval, type AssistantModel, type AssistantService, type ConversationDetails } from '@/lib/assistant-api'

export function ApprovalPanel({ approvals, busy = false, onDecision }: { approvals: Approval[]; busy?: boolean; onDecision: (approve: boolean) => void }) {
  if (!approvals.length) return null
  return <section className="ai-approval" aria-label="Pending Library changes">
    <h3 className="ai-approval-heading"><Icon name="triangle-alert" variant="control" tone="color" />Review Library changes</h3>
    {approvals.flatMap(approval => approval.action_requests).map((action, index) => <div className="ai-approval-action" key={index}><strong>{action.description || action.name.replaceAll('_', ' ')}</strong><pre>{JSON.stringify(action.args, null, 2)}</pre></div>)}
    <div className="ai-approval-buttons"><Button onClick={() => onDecision(true)} disabled={busy}>Approve changes<Icon name="check" variant="control" /></Button><Button variant="outline" onClick={() => onDecision(false)} disabled={busy}>Reject</Button></div>
  </section>
}

function LiveApproval({ onError }: { onError: (message: string) => void }) {
  const interrupts = useAgUiInterrupts()
  const submit = useAgUiSubmitInterruptResponses()
  const running = useAuiState(s => s.thread.isRunning)
  const [submitting, setSubmitting] = useState(false)
  const approvals: Approval[] = interrupts.map(interrupt => {
    const metadata = interrupt.metadata as { langgraph?: { raw?: { action_requests?: Approval['action_requests'] } }; action_requests?: Approval['action_requests'] } | undefined
    return { interrupt_id: interrupt.id, action_requests: metadata?.langgraph?.raw?.action_requests ?? metadata?.action_requests ?? [] }
  })
  async function decide(approve: boolean) {
    setSubmitting(true)
    try {
      if (approvals.some(approval => !approval.action_requests.length)) throw new Error('Reopen this conversation to load the pending changes before reviewing them.')
      await submit(approvals.map(approval => ({ interruptId: approval.interrupt_id, status: 'resolved', payload: { decisions: approval.action_requests.map(() => ({ type: approve ? 'approve' : 'reject' })) } })))
    } catch (error) { onError(error instanceof Error ? error.message : 'The approval could not be saved. Reopen this conversation.') }
    finally { setSubmitting(false) }
  }
  return <ApprovalPanel approvals={approvals} busy={running || submitting} onDecision={approve => { void decide(approve) }} />
}

function ConversationRuntime({ service, details, models, onCreated, onFinished, onBusy }: {
  service: AssistantService; details: ConversationDetails | null; models: AssistantModel[];
  onCreated: (id: string) => void; onFinished: () => void; onBusy: (busy: boolean) => void
}) {
  const [modelId, setModelId] = useState(models[0].id)
  const model = models.find(item => item.id === modelId) ?? models[0]
  const [effort, setEffort] = useState(model.efforts.includes('medium') ? 'medium' : model.efforts[0])
  const [error, setError] = useState<string | null>(null)
  const id = useRef(details?.id ?? null)
  const selection = useRef({ model, effort })
  const callbacks = useRef({ onCreated, onFinished, onBusy })
  useEffect(() => { selection.current = { model, effort }; callbacks.current = { onCreated, onFinished, onBusy } }, [model, effort, onCreated, onFinished, onBusy])
  const fetchTurn = useCallback(async (_url: string, init: RequestInit) => {
    setError(null)
    const input = RunAgentInputSchema.parse(JSON.parse(String(init.body)))
    const signal = init.signal ?? new AbortController().signal
    const { model, effort } = selection.current
    // Validate before creating metadata, so an invalid draft never creates an empty conversation.
    turnInput(input, id.current ?? input.threadId, model, effort)
    if (!id.current) {
      const user = input.messages.at(-1)
      const title = user?.role === 'user' ? typeof user.content === 'string' ? user.content : user.content.filter(part => part.type === 'text').map(part => part.text).join(' ') : 'New conversation'
      id.current = (await service.create(title, signal)).id
      callbacks.current.onCreated(id.current)
    }
    return service.run(turnInput(input, id.current, model, effort), signal)
  }, [service])
  const [agent] = useState(() => new HttpAgent({ url: '/api/v1/assistant:run', threadId: details?.id, fetch: fetchTurn }))
  const adapters = useMemo(() => {
    const images = new SimpleImageAttachmentAdapter()
    const attachments: AttachmentAdapter = { accept: 'image/png,image/jpeg,image/webp', add: async ({ file }) => {
      if (!selection.current.model.vision) throw new Error('Choose a vision model to attach an image.')
      if (file.size > 10_000_000) throw new Error('Use a PNG, JPEG or WebP image up to 10 MB.')
      return images.add({ file })
    }, remove: () => images.remove(), send: (attachment, options) => images.send(attachment, options) }
    return { attachments, history: {
      async load() {
        const messages = fromAgUiMessages(details?.state.messages ?? [])
        const approvals = details?.state.pending_approvals ?? []
        if (approvals.length) {
          const index = messages.findLastIndex(message => message.role === 'assistant')
          if (index < 0) throw new Error('Pending changes could not be restored. Reopen this conversation.')
          const message = messages[index]
          messages[index] = { ...message, status: { type: 'requires-action', reason: 'interrupt' }, metadata: { ...message.metadata, custom: { ...message.metadata?.custom, agui: { interrupts: approvals.map(approval => ({ id: approval.interrupt_id, reason: 'tool_call', metadata: { action_requests: approval.action_requests } })) } } } }
        }
        return ExportedMessageRepository.fromArray(messages)
      },
      // LangGraph persists the transcript and approvals on the server.
      async append() {},
    } }
  }, [details])
  const runtime = useAgUiRuntime({ agent, adapters, resumeTranscript: 'appended', autoCancelPendingToolCalls: false, onError: error => setError(error.message === 'assistant_failed' ? 'The response failed. Reopen this conversation to check its saved state.' : error.message) })
  useEffect(() => agent.subscribe({ onRunInitialized: () => callbacks.current.onBusy(true), onRunFinalized: () => { callbacks.current.onBusy(false); callbacks.current.onFinished() } }).unsubscribe, [agent])
  useEffect(() => () => { agent.abortRun(); callbacks.current.onBusy(false) }, [agent])
  function chooseModel(id: string) {
    const next = models.find(model => model.id === id)!
    setModelId(id)
    if (!next.efforts.includes(effort)) setEffort(next.efforts.includes('medium') ? 'medium' : next.efforts[0])
  }
  return <AssistantRuntimeProvider runtime={runtime}><AssistantThread models={models} model={model} effort={effort} onModel={chooseModel} onEffort={setEffort} error={error} clearError={() => setError(null)} footer={<LiveApproval onError={setError} />} usage={<UsageStatus />} /></AssistantRuntimeProvider>
}

function LiveAssistant({ initialId, remember, historyOpen, closeHistory, busy, setBusy, onTitleChange }: {
  initialId: string | null; remember: (id: string | null) => void; historyOpen: boolean; closeHistory: () => void; busy: boolean; setBusy: (busy: boolean) => void
  onTitleChange?: (title: string | null) => void
}) {
  const { services, scope } = useServices()
  const service = services.assistant!
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState(initialId)
  const [deleting, setDeleting] = useState<{ id: string; title: string } | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [version, setVersion] = useState(0)
  const models = useQuery({ queryKey: [scope, 'assistant-models'], queryFn: ({ signal }) => service.models(signal) })
  const detail = useQuery({ queryKey: [scope, 'assistant-conversation', selectedId, version], queryFn: ({ signal }) => service.details(selectedId!, signal), enabled: !!selectedId, staleTime: 0 })
  const history = useInfiniteQuery({ queryKey: [scope, 'assistant-conversations'], initialPageParam: undefined as string | undefined, queryFn: ({ pageParam, signal }) => service.list(pageParam, signal), getNextPageParam: page => page.next_cursor ?? undefined })
  useEffect(() => {
    if (detail.data?.title) onTitleChange?.(detail.data.title)
    else if (!selectedId) onTitleChange?.(null)
  }, [detail.data?.title, selectedId, onTitleChange])
  function select(id: string) { setSelectedId(id); remember(id); setVersion(value => value + 1); closeHistory() }
  const refresh = () => { void queryClient.invalidateQueries({ queryKey: [scope, 'assistant-conversations'] }); void queryClient.invalidateQueries({ queryKey: [services.mode, scope] }) }
  async function remove() {
    if (!deleting) return
    setDeleteBusy(true); setDeleteError('')
    try {
      await service.remove(deleting.id, new AbortController().signal)
      if (selectedId === deleting.id || initialId === deleting.id) { setSelectedId(null); remember(null); setVersion(value => value + 1) }
      setDeleting(null); refresh()
    } catch (error) { setDeleteError(error instanceof Error ? error.message : 'Could not delete this conversation.') }
    finally { setDeleteBusy(false) }
  }
  const failure = models.error ?? detail.error
  return <>
    <div className="ai-conversation-view" hidden={historyOpen}>
    {failure ? <div className="ai-state" role="alert"><h3>Couldn’t open PycilAI.</h3><p>{failure.message}</p><Button variant="outline" onClick={() => { void models.refetch(); void detail.refetch() }}>Retry</Button></div>
      : models.isPending || selectedId && detail.isPending ? <div className="ai-state" role="status">Opening your conversation…</div>
        : !models.data?.length ? <div className="ai-state"><h3>No models available.</h3><p>PycilAI needs a configured model before you can start a conversation.</p></div>
          : <ConversationRuntime key={`${selectedId ?? 'new'}:${version}`} service={service} details={selectedId ? detail.data! : null} models={models.data} onCreated={remember} onFinished={refresh} onBusy={setBusy} />}
    </div>
    {historyOpen && <section className="ai-history" aria-label="Conversation history"><div className="ai-history-header"><h3>Your conversations</h3><Button variant="ghost" size="icon" onClick={closeHistory} aria-label="Back to conversation"><Icon name="arrow-right" variant="control" /></Button></div>
      <div className="ai-history-list">{history.isPending ? <p className="ai-state" role="status">Loading conversations…</p> : history.isError ? <div className="ai-state" role="alert"><p>{history.error.message}</p><Button variant="outline" onClick={() => { void history.refetch() }}>Retry history</Button></div> : !history.data.pages.some(page => page.conversations.length) ? <div className="ai-state"><h3>Room for a new idea.</h3><p>Your conversations will appear here after you send a message.</p></div> : history.data.pages.flatMap(page => page.conversations).map(item => <div key={item.id} className="flex items-center"><button className="ai-conversation flex-1" aria-current={selectedId === item.id} disabled={busy} onClick={() => select(item.id)}><Icon name="book" tone="color" /><span><strong>{item.title || 'Untitled conversation'}</strong><small>{new Date(item.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</small></span></button><Button variant="ghost" size="icon" aria-label={`Delete conversation ${item.title || 'Untitled conversation'}`} disabled={busy} onClick={() => { setDeleting({ id: item.id, title: item.title || 'Untitled conversation' }); setDeleteError('') }}><Icon name="trash" variant="control" /></Button></div>)}
        {history.hasNextPage && <Button variant="outline" disabled={history.isFetchingNextPage} onClick={() => { void history.fetchNextPage() }}>{history.isFetchingNextPage ? 'Loading…' : 'Load older conversations'}</Button>}
      </div></section>}
    <AlertDialog open={Boolean(deleting)} onOpenChange={open => { if (!open && !deleteBusy) setDeleting(null) }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Delete conversation?</AlertDialogTitle><AlertDialogDescription>“{deleting?.title}” and its saved messages will be deleted.</AlertDialogDescription></AlertDialogHeader>{deleteError && <p role="alert">{deleteError}</p>}<AlertDialogFooter><AlertDialogCancel disabled={deleteBusy}>Cancel</AlertDialogCancel><Button variant="destructive" disabled={deleteBusy} onClick={() => { void remove() }}>{deleteBusy ? 'Deleting…' : 'Delete conversation'}</Button></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </>
}

export function PycilAI() {
  const { scope } = useServices()
  return <PycilAIPanel key={scope} />
}

function PycilAIPanel() {
  const { services, scope } = useServices()
  const account = useAccount()
  const { open, setOpen } = useAiPanelState()
  const [historyOpen, setHistoryOpen] = useState(false)
  const [newKey, setNewKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [lastId, setLastId] = useState<string | null>(() => {
    try { return typeof window === 'undefined' ? null : localStorage.getItem(`pycil:assistant:${scope}`) }
    catch { return null }
  })
  function remember(id: string | null) {
    setLastId(id)
    try { if (id) localStorage.setItem(`pycil:assistant:${scope}`, id); else localStorage.removeItem(`pycil:assistant:${scope}`) }
    catch { /* Server history remains available when browser storage is blocked. */ }
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

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    setIsResizing(true)
    const startX = e.clientX
    const startWidth = width

    const onPointerMove = (moveEvent: PointerEvent) => {
      const deltaX = startX - moveEvent.clientX
      const maxW = Math.min(920, window.innerWidth - 60)
      const nextWidth = Math.max(340, Math.min(startWidth + deltaX, maxW))
      setWidth(nextWidth)
      try { localStorage.setItem('pycil-ai-panel-width', String(nextWidth)) } catch {}
      document.documentElement.style.setProperty('--ai-panel-width', `${nextWidth}px`)
    }

    const onPointerUp = () => {
      setIsResizing(false)
      window.removeEventListener('pointermove', onPointerMove)
      window.removeEventListener('pointerup', onPointerUp)
    }

    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', onPointerUp)
  }, [width])

  const handleDoubleClick = useCallback(() => {
    setWidth(460)
    try { localStorage.setItem('pycil-ai-panel-width', '460') } catch {}
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
      const hasOpenOverlay = !!document.querySelector('[data-radix-popper-content-wrapper], [role="menu"], [role="listbox"]')
      if (hasOpenOverlay) return
      event.preventDefault()
      handleClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, handleClose])

  return <>
    <button
      ref={launcherRef}
      className="ai-launcher"
      data-open={open}
      aria-label="Open PycilAI"
      title="PycilAI"
      onClick={() => setOpen(true)}
    >
      <Icon name="spark" tone="color" className="size-6 shrink-0" />
    </button>
    {open && <aside className="ai-panel" aria-label="PycilAI">
      <div
        className="ai-resize-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize assistant panel"
        data-resizing={isResizing}
        onPointerDown={handlePointerDown}
        onDoubleClick={handleDoubleClick}
        title="Drag to resize, double-click to reset"
      />
      <header className="ai-header">
        <div className="ai-header-left">
          <button
            type="button"
            className="ai-chat-selector"
            onClick={() => setHistoryOpen(value => !value)}
            disabled={busy || !services.assistant || !account.signedIn}
            aria-label="Conversation selector"
            title={activeTitle || 'New AI chat'}
          >
            <span className="ai-chat-selector-title">{activeTitle || 'New AI chat'}</span>
            <Icon name="chevron-down" variant="control" className="size-3 shrink-0 text-muted-foreground" />
          </button>
        </div>
        <div className="ai-header-actions">
          <Button
            variant="ghost"
            size="icon"
            aria-label="New conversation"
            title="New conversation"
            disabled={busy || !services.assistant || !account.signedIn}
            onClick={() => { remember(null); setActiveTitle(null); setNewKey(value => value + 1); setHistoryOpen(false) }}
          >
            <Icon name="plus" variant="control" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Conversation history"
            title="Conversation history"
            disabled={busy || !services.assistant || !account.signedIn}
            onClick={() => setHistoryOpen(value => !value)}
          >
            <Icon name="history" />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Close PycilAI" title="Close panel" onClick={handleClose}>
            <Icon name="x" variant="control" />
          </Button>
        </div>
      </header>
      <div className="ai-panel-body">
        {!services.assistant ? <div className="ai-state"><AssistantGeometry /><h3>Meet PycilAI.</h3><p>AI conversations are available in the live app. Explore the components in the design workshop.</p><Button variant="outline" asChild><Link href="/showcase?view=assistant">Open assistant showcase</Link></Button></div>
          : !account.signedIn ? <div className="ai-state"><AssistantGeometry /><h3>A place for your questions.</h3><p>Sign in to chat with PycilAI and return to your saved conversations.</p><Button asChild><Link href="/login">Sign in</Link></Button></div>
            : <LiveAssistant key={`${scope}:${newKey}`} initialId={lastId} remember={remember} historyOpen={historyOpen} closeHistory={() => setHistoryOpen(false)} busy={busy} setBusy={setBusy} onTitleChange={setActiveTitle} />}
      </div>
    </aside>}
  </>
}
