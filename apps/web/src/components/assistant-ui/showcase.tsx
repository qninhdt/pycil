'use client'

import { useState } from 'react'
import { AssistantRuntimeProvider, SimpleImageAttachmentAdapter, useLocalRuntime, type ThreadMessageLike } from '@assistant-ui/react'
import { Icon } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { AssistantThread } from './thread'
import { ApprovalPanel } from './pycil-ai'
import type { AssistantModel } from '@/lib/assistant-api'

const models: AssistantModel[] = [
  { id: 'preview-vision', name: 'Vision model · Preview', vision: true, efforts: ['low', 'medium', 'high'] },
  { id: 'preview-text', name: 'Text model · Preview', vision: false, efforts: ['low', 'medium', 'high'] },
]
const initialMessages: ThreadMessageLike[] = [
  { role: 'user', content: 'What’s the difference between “discover” and “invent”?' },
  { role: 'assistant', content: [
    { type: 'reasoning', text: 'A short illustrative reasoning summary: compare finding something that already exists with creating something new, then give one example of each.' },
    { type: 'text', text: '**Discover** means to find something that already exists. **Invent** means to create something new.\n\n> You discover a new meaning. You invent a new way to remember it.\n\n- Scientists **discovered** penicillin.\n- People **invented** the telephone.\n\nTry writing one sentence with each word.' },
    { type: 'tool-call', toolCallId: 'preview-search', toolName: 'search_words', args: { query: 'discover' }, argsText: '{"query":"discover"}', result: { word: 'discover', source: 'Illustrative Dictionary result' } },
  ] },
]

export function AssistantShowcase() {
  const [modelId, setModelId] = useState(models[0].id)
  const [effort, setEffort] = useState('medium')
  const [empty, setEmpty] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [approval, setApproval] = useState(false)
  const [decision, setDecision] = useState('')
  const [error, setError] = useState<string | null>(null)
  const model = models.find(item => item.id === modelId)!
  const runtime = useLocalRuntime({ async *run() {
    yield { content: [{ type: 'reasoning' as const, text: 'This is an illustrative reasoning summary in the design preview.' }] }
    await new Promise(resolve => setTimeout(resolve, 250))
    yield { content: [{ type: 'reasoning' as const, text: 'This is an illustrative reasoning summary in the design preview.' }, { type: 'text' as const, text: 'This is a **design preview**. In the live app, PycilAI connects to your configured model and saves the conversation to your account.\n\nTry the model menu, attach an image, or open the conversation history.' }] }
  } }, { initialMessages, adapters: { attachments: new SimpleImageAttachmentAdapter() } })
  function toggleEmpty() { runtime.thread.reset(empty ? initialMessages : []); setEmpty(value => !value); setDecision('') }
  return <div className="ai-showcase">
    <div className="flex flex-wrap items-center justify-between gap-4 mb-6"><div><h2 className="text-[32px] font-extrabold tracking-[-.03em]">An assistant, in good form.</h2><p className="text-sm text-muted-foreground mt-3 max-w-[55ch]">The actual assistant-ui primitives. Rectangular messages, authored geometry, and room to think.</p></div><div className="flex flex-wrap gap-2"><Button variant="outline" onClick={toggleEmpty}>{empty ? 'Show conversation' : 'Empty state'}</Button><Button variant="outline" onClick={() => { setApproval(value => !value); setDecision('') }}>Approval state</Button><Button variant="outline" onClick={() => setError('The connection was interrupted. Reopen this conversation to check what was saved.')}>Error state</Button></div></div>
    <div className="ai-showcase-frame"><header className="ai-header"><div className="ai-header-left"><button type="button" className="ai-chat-selector" onClick={() => setHistoryOpen(value => !value)} aria-label="Conversation selector"><span className="ai-chat-selector-title">Preview AI chat</span><Icon name="chevron-down" variant="control" className="size-3 shrink-0 text-muted-foreground" /></button></div><div className="ai-header-actions"><Button variant="ghost" size="icon" aria-label="New preview conversation" onClick={() => { runtime.thread.reset([]); setEmpty(true); setHistoryOpen(false); setApproval(false); setDecision('') }}><Icon name="plus" variant="control" /></Button><Button variant="ghost" size="icon" aria-label="Preview conversation history" onClick={() => setHistoryOpen(value => !value)}><Icon name="book" /></Button></div></header>
      <p className="ai-preview-caption">Design preview · Illustrative messages and model names · Nothing is saved</p>
      <div className="ai-panel-body"><div className="ai-conversation-view" hidden={historyOpen}><AssistantRuntimeProvider runtime={runtime}><AssistantThread models={models} model={model} effort={effort} onModel={setModelId} onEffort={setEffort} error={error} clearError={() => setError(null)} footer={<>{approval && <ApprovalPanel approvals={[{ interrupt_id: 'preview', action_requests: [{ name: 'create_node', description: 'Create a deck in Personal', args: { name: 'Words worth keeping', type: 'DECK', parent: 'Personal' } }] }]} onDecision={approve => { setApproval(false); setDecision(approve ? 'Preview approved. No Library changes were made.' : 'Preview rejected. No Library changes were made.') }} />}{decision && <p className="text-xs py-4" role="status">{decision}</p>}</>} /></AssistantRuntimeProvider></div>
        {historyOpen && <section className="ai-history" aria-label="Preview conversation history"><div className="ai-history-header"><h3>Your conversations</h3><Button variant="ghost" size="icon" aria-label="Back to preview conversation" onClick={() => setHistoryOpen(false)}><Icon name="arrow-right" variant="control" /></Button></div><div className="ai-history-list">{['Discover or invent?', 'Words worth keeping', 'A plan for this week'].map(title => <button className="ai-conversation" key={title} onClick={() => { runtime.thread.reset(title === 'Discover or invent?' ? initialMessages : [{ role: 'user', content: title }, { role: 'assistant', content: 'Illustrative saved conversation. The live app loads your own conversation history.' }]); setHistoryOpen(false) }}><Icon name="book" tone="color" /><span><strong>{title}</strong><small>Illustrative conversation</small></span></button>)}</div></section>}
      </div>
    </div>
  </div>
}
