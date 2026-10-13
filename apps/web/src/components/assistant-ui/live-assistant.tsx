'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslations } from 'next-intl'
import { HttpAgent } from '@ag-ui/client'
import { RunAgentInputSchema } from '@ag-ui/core'
import { AssistantRuntimeProvider, ExportedMessageRepository, SimpleImageAttachmentAdapter, fromThreadMessageLike, useAuiState, type AttachmentAdapter, type ThreadMessage } from '@assistant-ui/react'
import { fromAgUiMessages, useAgUiRuntime, useAgUiInterrupts, useAgUiSubmitInterruptResponses } from '@assistant-ui/react-ag-ui'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Icon } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel } from '@/components/ui/alert-dialog'
import { cn } from 'cn'
import { useAiPanelState } from '@/hooks/use-ai-panel-state'
import { currentAssistantView } from '@/hooks/use-assistant-view'
import { useServices } from '@/lib/services/provider'
import { useAccount } from '@/components/application/providers'
import { AssistantThread, AssistantGeometry } from './thread'
import { AssistantError, turnInput, type Approval, type AssistantModel, type AssistantService, type ConversationDetails } from '@/lib/assistant-api'
import { getApiBaseUrl } from '@/lib/services/config'

export function ApprovalPanel({ approvals, busy = false, onDecision }: { approvals: Approval[]; busy?: boolean; onDecision: (approve: boolean) => void }) {
  const t = useTranslations('assistant')
  if (!approvals.length) return null
  return <section className="ai-approval" aria-label={t('pendingChanges')}>
    <h3 className="ai-approval-heading"><Icon name="triangle-alert" variant="control" tone="color" />{t('reviewChanges')}</h3>
    {approvals.flatMap(approval => approval.action_requests).map((action, index) => <div className="ai-approval-action" key={index}><strong>{action.description || action.name.replaceAll('_', ' ')}</strong><pre>{JSON.stringify(action.args, null, 2)}</pre></div>)}
    <div className="ai-approval-buttons"><Button onClick={() => onDecision(true)} disabled={busy}>{t('approveChanges')}<Icon name="check" variant="control" /></Button><Button variant="outline" onClick={() => onDecision(false)} disabled={busy}>{t('reject')}</Button></div>
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
  const [snapshot, setSnapshot] = useState<ThreadMessage[]>([])
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
    const view = currentAssistantView()
    turnInput(input, id.current ?? input.threadId, model, effort, view)
    if (!id.current) {
      const user = input.messages.at(-1)
      const title = user?.role === 'user' ? typeof user.content === 'string' ? user.content : user.content.filter(part => part.type === 'text').map(part => part.text).join(' ') : 'New conversation'
      id.current = (await service.create(title, signal)).id
      callbacks.current.onCreated(id.current)
    }
    return service.run(turnInput(input, id.current, model, effort, view), signal)
  }, [service])
  const [agent] = useState(() => new HttpAgent({ url: `${getApiBaseUrl()}/assistant:run`, threadId: details?.id, fetch: fetchTurn }))
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
  useEffect(() => agent.subscribe({
    onRunInitialized: () => callbacks.current.onBusy(true),
    onMessagesSnapshotEvent: ({ event }) => {
      setSnapshot(fromAgUiMessages(event.messages).map(message => fromThreadMessageLike(message, message.id!, { type: 'complete', reason: 'unknown' })))
    },
    onRunFinalized: () => { callbacks.current.onBusy(false); callbacks.current.onFinished() },
  }).unsubscribe, [agent])
  useEffect(() => () => { agent.abortRun(); callbacks.current.onBusy(false) }, [agent])
  function chooseModel(id: string) {
    const next = models.find(model => model.id === id)!
    setModelId(id)
    if (!next.efforts.includes(effort)) setEffort(next.efforts.includes('medium') ? 'medium' : next.efforts[0])
  }
  return <AssistantRuntimeProvider runtime={runtime}><AssistantThread models={models} model={model} effort={effort} onModel={chooseModel} onEffort={setEffort} error={error} clearError={() => setError(null)} footer={<LiveApproval onError={setError} />} usage={null} snapshot={snapshot} /></AssistantRuntimeProvider>
}

export function LiveAssistant({ initialId, remember, historyOpen, closeHistory, busy, setBusy, onTitleChange }: {
  initialId: string | null; remember: (id: string | null) => void; historyOpen: boolean; closeHistory: () => void; busy: boolean; setBusy: (busy: boolean) => void
  onTitleChange?: (title: string | null) => void
}) {
  const { services, scope } = useServices()
  const t = useTranslations('assistant')
  const tCommon = useTranslations('common')
  const service = services.assistant!
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState(initialId)
  const [deleting, setDeleting] = useState<{ id: string; title: string } | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [version, setVersion] = useState(0)
  const models = useQuery({ queryKey: [scope, 'assistant-models'], queryFn: ({ signal }) => service.models(signal) })
  const detail = useQuery({ queryKey: [scope, 'assistant-conversation', selectedId, version], queryFn: ({ signal }) => service.details(selectedId!, signal), enabled: !!selectedId, staleTime: 0,
    retry: (count, error) => !(error instanceof AssistantError && error.status === 404) && count < 3 })
  const history = useInfiniteQuery({ queryKey: [scope, 'assistant-conversations'], initialPageParam: undefined as string | undefined, queryFn: ({ pageParam, signal }) => service.list(pageParam, signal), getNextPageParam: page => page.next_cursor ?? undefined })
  useEffect(() => {
    if (selectedId && detail.error instanceof AssistantError && detail.error.status === 404) {
      setSelectedId(null)
      remember(null)
    }
  }, [selectedId, detail.error, remember])
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
    } catch (error) { setDeleteError(error instanceof Error ? error.message : t('couldNotDeleteConversation')) }
    finally { setDeleteBusy(false) }
  }
  const failure = models.error ?? detail.error
  return <>
    <div className="ai-conversation-view" hidden={historyOpen}>
    {failure ? <div className="ai-state" role="alert"><h3>{t('couldNotOpenAi')}</h3><p>{failure.message}</p><Button variant="outline" onClick={() => { void models.refetch(); void detail.refetch() }}>{tCommon('retry')}</Button></div>
      : models.isPending || selectedId && detail.isPending ? <div className="ai-state" role="status">{t('openingConversation')}</div>
        : !models.data?.length ? <div className="ai-state"><h3>{t('noModelsAvailable')}</h3><p>{t('noModelsAvailableDesc')}</p></div>
          : <ConversationRuntime key={`${selectedId ?? 'new'}:${version}`} service={service} details={selectedId ? detail.data! : null} models={models.data} onCreated={remember} onFinished={refresh} onBusy={setBusy} />}
    </div>
    {historyOpen && <section className="ai-history" aria-label={t('conversationHistory')}>
      <div className="flex items-center justify-between px-3.5 py-2 border-b border-border bg-accent/20 flex-none">
        <Button
          variant="ghost"
          size="sm"
          onClick={closeHistory}
          aria-label={t('backToConversation')}
          className="h-7 gap-1.5 px-2 text-xs font-bold -ml-1 hover:bg-accent"
        >
          <ArrowLeft className="size-3.5" aria-hidden="true" />
          <span>{tCommon('back')}</span>
        </Button>
        <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
          {t('conversations')}
        </span>
      </div>
      <div className="ai-history-list">
        {history.isPending ? <p className="ai-state shimmer text-foreground/50 font-medium" role="status">{t('loadingConversations')}</p>
          : history.isError ? <div className="ai-state" role="alert"><p>{history.error.message}</p><Button variant="outline" onClick={() => { void history.refetch() }}>{t('retryHistory')}</Button></div>
          : !history.data.pages.some(page => page.conversations.length) ? <div className="ai-state"><h3>{t('roomForNewIdea')}</h3><p>{t('conversationsEmptyDesc')}</p></div>
          : (history.data.pages.flatMap(page => page.conversations) ?? [])
              .slice()
              .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
              .map(item => (
                <div
                  key={item.id}
                  className={cn(
                    'ai-history-row group relative flex items-center w-full border-b border-border transition-colors duration-150',
                    selectedId === item.id ? 'bg-accent/80 border-l border-l-art-blue' : 'hover:bg-accent'
                  )}
                  data-active={selectedId === item.id}
                >
                  <button
                    type="button"
                    className="ai-conversation flex-1"
                    aria-current={selectedId === item.id}
                    disabled={busy}
                    onClick={() => select(item.id)}
                  >
                    <Icon name="book" tone={selectedId === item.id ? 'color' : 'mono'} />
                    <span>
                      <strong>{item.title || t('untitledConversation')}</strong>
                      <small>{new Date(item.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</small>
                    </span>
                  </button>
                  <Button
                    variant="ghost"
                    size="icon-xs"
                    className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity mr-3 flex-none hover:text-destructive hover:bg-destructive/10"
                    aria-label={t('deleteConversationAria', { title: item.title || t('untitledConversation') })}
                    disabled={busy}
                    onClick={() => {
                      setDeleting({ id: item.id, title: item.title || t('untitledConversation') })
                      setDeleteError('')
                    }}
                  >
                    <Icon name="trash" variant="control" className="size-3.5" />
                  </Button>
                </div>
              ))}
        {history.hasNextPage && (
          <div className="p-4 flex justify-center border-t border-border">
            <Button
              variant="outline"
              size="sm"
              disabled={history.isFetchingNextPage}
              onClick={() => { void history.fetchNextPage() }}
            >
              {history.isFetchingNextPage ? tCommon('loading') : t('loadOlderConversations')}
            </Button>
          </div>
        )}
      </div></section>}
    <AlertDialog open={Boolean(deleting)} onOpenChange={open => { if (!open && !deleteBusy) setDeleting(null) }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{t('deleteConversationTitle')}</AlertDialogTitle><AlertDialogDescription>{t('deleteConversationDesc', { title: deleting?.title ?? '' })}</AlertDialogDescription></AlertDialogHeader>{deleteError && <p role="alert">{deleteError}</p>}<AlertDialogFooter><AlertDialogCancel disabled={deleteBusy}>{tCommon('cancel')}</AlertDialogCancel><Button variant="destructive" disabled={deleteBusy} onClick={() => { void remove() }}>{deleteBusy ? tCommon('deleting') : t('deleteConversation')}</Button></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </>
}
