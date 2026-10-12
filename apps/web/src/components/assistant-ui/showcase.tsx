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

const personalId = '01900000-0000-7000-8000-000000000001'
const deckId = '01900000-0000-7000-8000-000000000002'
const previewSummary = { node_id: personalId, as_of: '2026-10-10T08:15:00Z', total: 132, new: 4, studied: 128, due: 16, not_due: 112, reachable_decks: 5, last_studied_at: '2026-10-09T18:40:00Z' }
const previewNode = { node_id: deckId, name: 'Executive & Board Discourse', type: 'DECK', parent_id: personalId, space: 'PERSONAL', editable: true, path: [{ node_id: personalId, name: 'Personal' }, { node_id: deckId, name: 'Executive & Board Discourse' }] }

export const MASTER_CONVERSATION: ThreadMessageLike[] = [
  // Turn 1: Daily Diagnostic & Spaced-Repetition Backlog Check
  {
    role: 'user',
    content: 'Good morning! I have a 20-minute study window before my executive sync today. Could you check my spaced-repetition retention metrics across my library and advise me on whether I should clear my review queue or take in new vocabulary?',
  },
  {
    role: 'assistant',
    content: [
      {
        type: 'reasoning',
        text: '1. Inspect the learner\'s cross-deck spaced repetition backlog via `learning_overview`.\n2. Evaluate due cards against new intake queue. Memory consolidation research (Ebbinghaus forgetting curve & Leitner spacing) shows that delaying overdue cards exponentially increases retrieval latency and relapse rates.\n3. Prepare structured recommendations: prioritize clearing reviews within the 20-minute window before intaking novel terminology.',
      },
      {
        type: 'tool-call',
        toolCallId: 'preview-tool-progress',
        toolName: 'learning_overview',
        args: {},
        argsText: '{}',
        result: { summaries: [previewSummary] },
      },
      {
        type: 'text',
        text: 'Good morning! Here is your spaced-repetition retention diagnostic for today:\n\n- **16 cards due for immediate review** across 5 active decks.\n- **4 new cards** buffered in your intake queue.\n- **128 studied cards**, including the cards due today.\n- *Last reviewed:* yesterday at 18:40 UTC.\n\n> **Pedagogical Recommendation:**\n> Allocate your first **12–15 minutes** exclusively to clearing the **16 due cards**. Spaced-repetition scheduling preserves optimal retrieval memory when reviews are cleared on schedule.\n>\n> Once cleared, use the remaining time to explore new high-leverage vocabulary for your meetings!',
      },
    ],
  },

  // Turn 2: Lexical Nuance Exploration & Semantic Comparison
  {
    role: 'user',
    content: 'Understood, I will clear those cards during my commute. During yesterday\'s strategy sync, two contrasting terms came up: "pragmatic" and "dogmatic". Could you look up their formal dictionary records, analyze how their connotations differ in professional leadership, and show me how they operate in context?',
  },
  {
    role: 'assistant',
    content: [
      {
        type: 'reasoning',
        text: '1. Query the English lexicon using `search_words` for \'pragmatic\' and \'dogmatic\' to retrieve verified phonetics, grammatical forms, and lexical tiers.\n2. Contrast their connotations:\n   - \'Pragmatic\' (Greek: \'pragma\' - deed/action): Grounded in observable reality, prioritizing functional efficacy over doctrine. High prestige in executive circles.\n   - \'Dogmatic\' (Greek: \'dogma\' - opinion/tenet): Inflexible adherence to fixed doctrine regardless of empirical counter-evidence. Often pejorative in leadership contexts.\n3. Provide concrete sentence frames illustrating the contrast in an engineering/executive scenario.',
      },
      {
        type: 'tool-call',
        toolCallId: 'preview-tool-search-pragmatic',
        toolName: 'search_words',
        args: { queries: ['pragmatic', 'dogmatic'], limit: 1 },
        argsText: '{"queries":["pragmatic","dogmatic"],"limit":1}',
        result: {
          items: [
            {
              kind: 'WORD',
              word_id: 1042,
              lemma: 'pragmatic',
              entry_type: 'WORD',
              match_kind: 'EXACT',
              matched_surface: 'pragmatic',
              matched_queries: ['pragmatic'],
              senses: [{ sense_id: 2042, word_id: 1042, lemma: 'pragmatic', pos: 'ADJECTIVE', definition: 'Dealing with things sensibly and realistically.' }],
            },
            {
              kind: 'WORD',
              word_id: 1043,
              lemma: 'dogmatic',
              entry_type: 'WORD',
              match_kind: 'EXACT',
              matched_surface: 'dogmatic',
              matched_queries: ['dogmatic'],
              senses: [{ sense_id: 2043, word_id: 1043, lemma: 'dogmatic', pos: 'ADJECTIVE', definition: 'Insisting that your beliefs are right without considering evidence.' }],
            },
          ],
          unmatched_queries: [],
        },
      },
      {
        type: 'text',
        text: 'Here is the comparative lexical analysis for both terms:\n\n### 1. **Pragmatic** /præɡˈmæt.ɪk/ *(adjective · CEFR C1)*\n- **Definition**: Dealing with things sensibly and realistically in a way that is based on practical rather than theoretical considerations.\n- **Leadership Connotation**: **Commendatory**. Signifies agility, outcome-orientation, and emotional maturity.\n- **Collocations**: *pragmatic compromise*, *pragmatic roadmap*, *pragmatic governance*.\n- **Executive Example**:\n  > *“Faced with unexpected API latency, the engineering director took a **pragmatic** stance, caching intermediate payloads rather than delaying the quarter\'s launch.”*\n\n---\n\n### 2. **Dogmatic** /dɒɡˈmæt.ɪk/ *(adjective · CEFR C2)*\n- **Definition**: Characterized by the assertion of unproved or unprovable principles, refusing to entertain debate or empirical dissonance.\n- **Leadership Connotation**: **Cautionary / Pejorative**. Suggests rigidity, ideological hubris, and unwillingness to adapt to changing market conditions.\n- **Collocations**: *dogmatic adherence*, *dogmatic stance*, *dogmatically oppose*.\n- **Executive Example**:\n  > *“The committee\'s **dogmatic** refusal to consider managed cloud solutions resulted in severe operational bottlenecks.”*\n\n| Dimension | Pragmatic | Dogmatic |\n| :--- | :--- | :--- |\n| **Core Driver** | Observable outcomes & constraints | Unquestioned doctrine or dogma |\n| **Cognitive Stance** | Adaptive, empirical, contextual | Fixed, doctrinaire, unyielding |\n| **Executive Impact** | Unblocks friction & accelerates velocity | Stifles innovation & alienates stakeholders |',
      },
    ],
  },

  // Turn 3: Library Audit, Deck Creation & Inspection
  {
    role: 'user',
    content: 'That comparison table is crystal clear. I want to save these into a dedicated deck. Can you check what\'s currently in my "Personal" workspace, create a new deck named "Executive & Board Discourse" there, and verify its configuration?',
  },
  {
    role: 'assistant',
    content: [
      {
        type: 'reasoning',
        text: '1. Inspect the \'Personal\' library node via `read_library` (STRUCTURE) to audit existing decks and verify no name collisions exist.\n2. Invoke `create_node` to provision a new DECK titled \'Executive & Board Discourse\' under \'Personal\'.\n3. Follow up with `read_library` (CONTENT) on the newly provisioned deck ID to confirm metadata, zero initial card count, and active parent relationship.',
      },
      {
        type: 'tool-call',
        toolCallId: 'preview-tool-list-nodes',
        toolName: 'read_library',
        args: { node_id: personalId, view: 'STRUCTURE' },
        argsText: JSON.stringify({ node_id: personalId, view: 'STRUCTURE' }),
        result: {
          node: { node_id: personalId, name: 'Personal', type: 'FOLDER' },
          summary: previewSummary,
          nodes: [
            { name: 'Strategic Negotiations', type: 'DECK', summary: { total: 24 } },
            { name: 'Technical Architecture', type: 'DECK', summary: { total: 38 } },
            { name: 'Product Discovery', type: 'FOLDER', summary: { total: 4 } },
            { name: 'Meeting Idioms', type: 'DECK', summary: { total: 19 } },
          ],
          next_cursor: null,
        },
      },
      {
        type: 'tool-call',
        toolCallId: 'preview-tool-create-node',
        toolName: 'create_node',
        args: { name: 'Executive & Board Discourse', type: 'DECK', parent_id: personalId },
        argsText: JSON.stringify({ name: 'Executive & Board Discourse', type: 'DECK', parent_id: personalId }),
        result: { ...previewNode, sense_count: 0, summary: { total: 0 } },
      },
      {
        type: 'tool-call',
        toolCallId: 'preview-tool-get-node',
        toolName: 'read_library',
        args: { node_id: deckId },
        argsText: JSON.stringify({ node_id: deckId }),
        result: {
          node: previewNode,
          summary: { total: 0 },
          senses: [],
          next_cursor: null,
        },
      },
      {
        type: 'text',
        text: 'Done! Here is what was completed in your Library:\n\n1. **Workspace Audited**: Found 3 existing decks (*Strategic Negotiations*, *Technical Architecture*, *Meeting Idioms*) and 1 folder (*Product Discovery*) in `Personal`. No collisions detected.\n2. **Deck Created**: Successfully initialized **Executive & Board Discourse** (`DECK`).\n3. **Verified**: Verified deck state—ready with parent link to `Personal Library`.\n\nWould you like me to commit **pragmatic** and **dogmatic** into this deck and generate an interactive recall exercise?',
      },
    ],
  },

  // Turn 4: Word Ingestion & Contextual Active-Recall Challenge
  {
    role: 'user',
    content: 'Yes please! Commit both words to the new deck with their pronunciations and collocations, and give me a quick active-recall cloze challenge right now so I can test my understanding before heading into my meeting.',
  },
  {
    role: 'assistant',
    content: [
      {
        type: 'reasoning',
        text: '1. Call `update_node` to add sense IDs [2042, 2043] into deck \'node-exec-board\'.\n2. Synthesize an authentic, high-context cloze challenge that requires discerning between pragmatic and dogmatic based on situational cues (flexibility vs dogmatic inflexibility).\n3. Provide an interactive prompt encouraging immediate recall.',
      },
      {
        type: 'tool-call',
        toolCallId: 'preview-tool-modify-senses',
        toolName: 'update_node',
        args: { node_id: deckId, add_sense_ids: [2042, 2043] },
        argsText: JSON.stringify({ node_id: deckId, add_sense_ids: [2042, 2043] }),
        result: { ...previewNode, added_count: 2, removed_count: 0, sense_count: 2, summary: { total: 2 } },
      },
      {
        type: 'text',
        text: 'Both **pragmatic** and **dogmatic** are now linked to **Executive & Board Discourse** with their existing lexical content!\n\n---\n\n### 🎯 Active Recall Challenge\n\nTest your situational judgment before your sync:\n\n**Context:**\n> *“During budget renegotiations, the security officer’s **(1) ____________** insistence on zero third-party software halted deployment for three weeks. In response, the Chief Information Officer negotiated a **(2) ____________** interim policy that allowed verified sandboxing while the full audit proceeded.”*\n\n**Select the correct terms:**\n- **Blank (1):** `[                 ]` *(pragmatic / dogmatic)*\n- **Blank (2):** `[                 ]` *(pragmatic / dogmatic)*\n\n*Hint:* One reflects inflexible doctrine regardless of delivery risks; the other reflects practical compromise to protect delivery velocity.\n\nWhenever you\'re ready, reply with your choice, or hit the **Approval state** toggle above if you want to inspect pending batch mutations!',
      },
    ],
  },
]

export const SCENARIOS = [
  {
    id: 'master' as const,
    name: 'Executive Workflow',
    description: 'Comprehensive multi-turn dialogue with learning analytics, dictionary lookup, library actions, and active recall.',
    messages: MASTER_CONVERSATION,
  },
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

  const runtime = useLocalRuntime(
    {
      async *run({ messages }) {
        const lastUser = messages.findLast(m => m.role === 'user')
        const rawContent = lastUser?.content
        const text = typeof rawContent === 'string'
          ? rawContent
          : Array.isArray(rawContent)
            ? (rawContent.find(p => p.type === 'text') as any)?.text ?? ''
            : ''

        yield {
          content: [
            {
              type: 'reasoning' as const,
              text: 'Analyzing learner response against retrieval criteria for executive terminology.',
            },
          ],
        }
        await new Promise(resolve => setTimeout(resolve, 350))

        const lower = text.toLowerCase()
        const isCorrect = lower.includes('dogmatic') && lower.includes('pragmatic')

        yield {
          content: [
            {
              type: 'reasoning' as const,
              text: 'Analyzing learner response against retrieval criteria for executive terminology.',
            },
            {
              type: 'text' as const,
              text: isCorrect
                ? '🎯 **Spot on!**\n\n1. **(1) dogmatic** captures the rigid, doctrinaire refusal to adapt.\n2. **(2) pragmatic** captures the realistic, outcome-focused compromise.\n\nThis is a design preview. Both cards have been scheduled with a 24-hour interval for your first active retrieval test tomorrow!'
                : 'This is a design preview. In the live app, PycilAI automatically evaluates your answer against the dictionary senses, tracks your spaced-repetition accuracy score, and schedules your next review.',
            },
          ],
        }
      },
    },
    { initialMessages: MASTER_CONVERSATION, adapters: { attachments: new SimpleImageAttachmentAdapter() } }
  )

  function toggleEmpty() {
    runtime.thread.reset(empty ? MASTER_CONVERSATION : [])
    setEmpty(value => !value)
    setDecision('')
  }

  return (
    <div className="ai-showcase">
      <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
        <div>
          <h2 className="text-[32px] font-extrabold tracking-[-.03em]">An assistant, in good form.</h2>
          <p className="text-sm text-muted-foreground mt-2 max-w-[55ch]">
            Executive workflow: spaced repetition diagnostic, lexical comparison, library node creation, and active recall.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={toggleEmpty}>
            {empty ? 'Show conversation' : 'Empty state'}
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              setApproval(value => !value)
              setDecision('')
            }}
          >
            {approval ? 'Hide approval' : 'Approval state'}
          </Button>
          <Button
            variant="outline"
            onClick={() => setError('The connection was interrupted. Reopen this conversation to check what was saved.')}
          >
            Error state
          </Button>
        </div>
      </div>

      <div className="ai-showcase-frame">
        <header className="ai-header">
          <div className="ai-header-left">
            <button
              type="button"
              className="ai-chat-selector"
              onClick={() => setHistoryOpen(value => !value)}
              aria-label="Conversation selector"
            >
              <span className="ai-chat-selector-title">Executive &amp; Board Discourse</span>
              <Icon name="chevron-down" variant="control" className="size-3 shrink-0 text-muted-foreground" />
            </button>
          </div>
          <div className="ai-header-actions">
            <Button
              variant="ghost"
              size="icon"
              aria-label="New preview conversation"
              onClick={() => {
                runtime.thread.reset([])
                setEmpty(true)
                setHistoryOpen(false)
                setApproval(false)
                setDecision('')
              }}
            >
              <Icon name="plus" variant="control" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Preview conversation history"
              onClick={() => setHistoryOpen(value => !value)}
            >
              <Icon name="book" />
            </Button>
          </div>
        </header>

        <p className="ai-preview-caption">
          Comprehensive multi-turn dialogue with learning analytics, dictionary lookup, library actions, and active recall.
        </p>

        <div className="ai-panel-body">
          <div className="ai-conversation-view" hidden={historyOpen}>
            <AssistantRuntimeProvider runtime={runtime}>
              <AssistantThread
                models={models}
                model={model}
                effort={effort}
                onModel={setModelId}
                onEffort={setEffort}
                error={error}
                clearError={() => setError(null)}
                footer={
                  <>
                    {approval && (
                      <ApprovalPanel
                        approvals={[
                          {
                            interrupt_id: 'preview-deck-mutation',
                            action_requests: [
                              {
                                name: 'update_node',
                                description: 'Add 2 senses ("pragmatic", "dogmatic") to "Executive & Board Discourse"',
                                args: {
                                  node_id: deckId,
                                  add_sense_ids: [2042, 2043],
                                },
                              },
                            ],
                          },
                        ]}
                        onDecision={approve => {
                          setApproval(false)
                          setDecision(
                            approve
                              ? 'Preview approved: 2 cards staged into "Executive & Board Discourse".'
                              : 'Preview rejected: No library changes were applied.'
                          )
                        }}
                      />
                    )}
                    {decision && (
                      <p className="text-xs py-4 text-muted-foreground" role="status">
                        {decision}
                      </p>
                    )}
                  </>
                }
              />
            </AssistantRuntimeProvider>
          </div>

          {historyOpen && (
            <section className="ai-history" aria-label="Preview conversation history">
              <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-accent/20 flex-none">
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label="Back to preview conversation"
                  onClick={() => setHistoryOpen(false)}
                  className="h-7 gap-1.5 px-2 text-xs font-bold -ml-1 hover:bg-accent"
                >
                  <Icon name="arrow-left" variant="control" />
                  <span>Back</span>
                </Button>
              </div>
              <div className="ai-history-list">
                <div className="ai-history-row">
                  <button
                    className="ai-conversation"
                    onClick={() => {
                      runtime.thread.reset(MASTER_CONVERSATION)
                      setEmpty(false)
                      setHistoryOpen(false)
                    }}
                  >
                    <Icon name="book" tone="color" />
                    <span>
                      <strong>Executive &amp; Board Discourse</strong>
                      <small>Active multi-step workflow · 4 turns</small>
                    </span>
                  </button>
                </div>
                <div className="ai-history-row">
                  <button
                    className="ai-conversation"
                    onClick={() => {
                      runtime.thread.reset([
                        { role: 'user', content: 'Words worth keeping' },
                        {
                          role: 'assistant',
                          content: 'Illustrative saved conversation. The live app loads your own conversation history.',
                        },
                      ])
                      setEmpty(false)
                      setHistoryOpen(false)
                    }}
                  >
                    <Icon name="book" tone="color" />
                    <span>
                      <strong>Words worth keeping</strong>
                      <small>Illustrative conversation</small>
                    </span>
                  </button>
                </div>
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
