'use client'

import React from 'react'
import { Icon, type CompactIconName } from '@/components/artwork/artwork'
import { parseWordSearch, type WordHit } from '@/lib/dictionary-model'
import { parseSummary } from '@/lib/home-api'

export interface ToolRendererProps {
  toolName: string
  args: any
  result: any
  status: { type: string }
  isError?: boolean
}

function safeParse(val: any) {
  if (typeof val === 'string') {
    try {
      return JSON.parse(val)
    } catch {
      return val
    }
  }
  return val
}

// 1. Dictionary Lookup Renderer (search_words)
function DictionaryResultView({ args, result }: { args: any; result: any }) {
  const pArgs = safeParse(args)
  const pResult = safeParse(result)

  const query = Array.isArray(pArgs?.queries) ? pArgs.queries.join(', ') : ''
  let items: WordHit[]
  try { items = parseWordSearch(pResult).items.filter((hit): hit is WordHit => hit.kind === 'WORD') }
  catch { return <p className="text-xs text-muted-foreground">Search results unavailable.</p> }
  const total = items.length

  return (
    <div className="ai-tool-content ai-tool-dict">
      <div className="flex items-center justify-between gap-2 mb-2 pb-2 border-b border-border text-[11px] text-muted-foreground">
        <span className="font-mono">Query: &ldquo;{query}&rdquo;</span>
        <span className="font-bold uppercase tracking-wider">{total} match{total > 1 ? 'es' : ''}</span>
      </div>
      {items.map(hit => {
        const label = hit.lemma
        return <div key={hit.word_id} className="flex flex-wrap items-baseline gap-2 py-1.5">
          <span className="text-[15px] font-extrabold tracking-tight text-foreground">{label}</span>
          {hit.matched_surface !== label && <small className="text-muted-foreground">Matched “{hit.matched_surface}”</small>}
          <small className="ml-auto text-muted-foreground">Ready</small>
        </div>
      })}
      {total === 0 && <p className="text-xs text-muted-foreground">No entries found.</p>}
    </div>
  )
}

// Exact learning summary.
function ProgressResultView({ result }: { result: any }) {
  let summary: ReturnType<typeof parseSummary>
  try { summary = parseSummary(safeParse(result)) }
  catch { return <p className="text-xs text-muted-foreground">Progress unavailable.</p> }
  const { due, new: newCards, studied, last_studied_at } = summary

  return (
    <div className="ai-tool-content ai-tool-progress">
      <div className="grid grid-cols-3 gap-2 mb-2 text-center">
        <div className="p-2 border border-border border-t-2 border-t-[var(--art-red)] bg-background">
          <div className="text-lg font-black tracking-tight text-foreground">{due}</div>
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mt-0.5">Due</div>
        </div>
        <div className="p-2 border border-border border-t-2 border-t-[var(--art-yellow)] bg-background">
          <div className="text-lg font-black tracking-tight text-foreground">{newCards}</div>
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mt-0.5">New</div>
        </div>
        <div className="p-2 border border-border border-t-2 border-t-[var(--art-blue)] bg-background">
          <div className="text-lg font-black tracking-tight text-foreground">{studied}</div>
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mt-0.5">Studied</div>
        </div>
      </div>
      <div className="flex items-center justify-between text-[11px] text-muted-foreground px-0.5 pt-1">
        <span>Last review: {last_studied_at
          ? <time dateTime={last_studied_at}>{new Date(last_studied_at).toLocaleString()}</time>
          : 'No reviews yet'}</span>
      </div>
    </div>
  )
}

// Library search and structure pages.
function NodesResultView({ args, result }: { args: any; result: any }) {
  const pArgs = safeParse(args)
  const pResult = safeParse(result)

  const query = Array.isArray(pArgs?.queries) ? pArgs.queries.join(', ') : ''
  const parent = pArgs?.node_id || ''
  if (!Array.isArray(pResult?.nodes)) return <p className="text-xs text-muted-foreground">Library results unavailable.</p>
  const items = pResult.nodes

  return (
    <div className="ai-tool-content ai-tool-nodes">
      <div className="flex items-center justify-between mb-2 pb-1.5 border-b border-border text-[11px] text-muted-foreground">
        <span>
          {query ? (
            <>Search: <strong className="text-foreground font-mono">&ldquo;{query}&rdquo;</strong></>
          ) : (
            <>Location: <strong className="text-foreground">{parent || 'Personal Library'}</strong></>
          )}
        </span>
        <span>{items.length} item{items.length !== 1 ? 's' : ''}</span>
      </div>
      {items.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          {items.slice(0, 6).map((item: any, idx: number) => {
            const isFolder = item.type === 'FOLDER'
            return (
              <div key={idx} className="flex items-center justify-between gap-2 p-1.5 border border-border bg-background text-xs">
                <div className="flex items-center gap-2 min-w-0">
                  <Icon name={isFolder ? 'folder' : 'document'} variant="control" className="size-3.5 shrink-0 text-muted-foreground" />
                  <span className="font-bold truncate text-foreground">{item.name}</span>
                </div>
                <span className="text-[10px] text-muted-foreground font-mono shrink-0">
                  {item.summary?.total !== undefined ? `${item.summary.total} cards` : isFolder ? 'Folder' : 'Deck'}
                </span>
              </div>
            )
          })}
          {items.length > 6 && (
            <p className="text-[10px] text-muted-foreground text-center pt-1">+ {items.length - 6} more items</p>
          )}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground italic py-1">
          {query ? `No items found matching "${query}".` : 'No folders or decks found.'}
        </p>
      )}
    </div>
  )
}

// Library metadata.
const nodeTypes: Record<string, string> = { FOLDER: 'Folder', DECK: 'Deck', REFERENCE: 'Reference' }

function NodeDetailView({ result }: { result: any }) {
  const parsed = safeParse(result)
  const pResult = parsed?.node
  const name = pResult?.name || 'Node details'
  const parent = pResult?.path?.find((node: { node_id: string }) => node.node_id === pResult?.parent_id)?.name ?? pResult?.parent_id
  const count = parsed?.summary?.total
  const updated = pResult?.updated_at

  return (
    <div className="ai-tool-content ai-tool-deck">
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <h4 className="text-sm font-extrabold text-foreground">{name}</h4>
          {parent && <p className="text-[11px] text-muted-foreground mt-0.5">Parent: {parent}</p>}
        </div>
        {typeof count === 'number' && <span className="inline-flex px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider border border-foreground bg-accent">
          {count} cards
        </span>}
      </div>
      <div className="pt-2 border-t border-border flex justify-between text-[11px] text-muted-foreground">
        <span>Type: <strong>{nodeTypes[pResult?.type] ?? 'Unknown'}</strong></span>
        {updated && <span>Updated: <time dateTime={updated}>{new Date(updated).toLocaleString()}</time></span>}
      </div>
    </div>
  )
}

// Saved Library changes.
function MutationResultView({ toolName, args, result }: { toolName: string; args: any; result: any }) {
  const pArgs = safeParse(args)
  const pResult = safeParse(result)
  const isCreate = toolName === 'create_node'
  const name = pResult?.name || pArgs?.name || 'Library item'
  const type = nodeTypes[pResult?.type ?? pArgs?.type] ?? 'Item'
  const parent = pResult?.parent_id ?? pArgs?.parent_id

  return (
    <div className="ai-tool-content ai-tool-mutation">
      <div className="flex items-center gap-2 mb-1.5">
        <span className={`inline-flex items-center justify-center size-4 border border-foreground text-[10px] font-bold bg-[var(--art-yellow)] text-foreground`}>
          +
        </span>
        <span className="text-xs font-bold text-foreground">
          {isCreate ? `Created ${type}: "${name}"` : `Updated: "${name}"`}
        </span>
      </div>
      {parent && <p className="text-[11px] text-muted-foreground pl-6">
        {`Target location: ${parent}`}
      </p>}
    </div>
  )
}

function VocabularyResultView({ senses }: { senses: any[] }) {
  return <div className="ai-tool-content">{senses.length ? senses.map(sense => <section key={sense.sense_id} className="py-2 border-b border-border text-xs">
    <strong>{sense.lemma}</strong><span className="ml-2 text-muted-foreground">{sense.pos?.toLowerCase()}</span>
    <p className="mt-1">{sense.definition ?? 'Definition unavailable.'}</p>
    {sense.examples?.map((example: string, index: number) => <p className="mt-1 text-muted-foreground" key={index}>{example}</p>)}
    {sense.learning && <p className="mt-1 text-muted-foreground">{sense.learning.state}{sense.learning.level != null && ` · Level ${sense.learning.level}`}</p>}
  </section>) : <p className="text-xs text-muted-foreground">No senses found.</p>}</div>
}

// 6. Generic Clean Key-Value Fallback (no raw JSON dump)
function GenericCleanView({ args, result }: { args: any; result: any }) {
  const pArgs = safeParse(args)
  const pResult = safeParse(result)
  const cleanPairs: { key: string; value: string }[] = []

  const inspect = (obj: any, prefix = '') => {
    if (!obj || typeof obj !== 'object') return
    for (const [k, v] of Object.entries(obj)) {
      if (v === null || v === undefined) continue
      if (typeof v === 'object' && !Array.isArray(v)) {
        inspect(v, `${k}.`)
      } else {
        cleanPairs.push({
          key: `${prefix}${k}`.replace(/_/g, ' '),
          value: Array.isArray(v) ? `${v.length} items` : String(v),
        })
      }
    }
  }

  inspect(pArgs, 'param: ')
  if (pResult && typeof pResult === 'object') {
    inspect(pResult, '')
  } else if (pResult !== undefined) {
    cleanPairs.push({ key: 'result', value: String(pResult) })
  }

  return (
    <div className="ai-tool-content ai-tool-generic">
      {cleanPairs.length > 0 ? (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[11px]">
          {cleanPairs.slice(0, 8).map((pair, idx) => (
            <div key={idx} className="flex flex-col border-b border-border pb-1">
              <span className="font-bold uppercase tracking-wider text-[10px] text-muted-foreground">{pair.key}</span>
              <span className="text-foreground truncate font-mono mt-0.5">{pair.value}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground italic">Executed successfully.</p>
      )}
    </div>
  )
}

export const toolTitles: Record<string, { title: string; icon: CompactIconName; tone?: 'color' | 'mono' }> = {
  search_words: { title: 'Dictionary Lookup', icon: 'dictionary', tone: 'color' },
  read_vocabulary: { title: 'Vocabulary', icon: 'dictionary', tone: 'color' },
  read_library: { title: 'Library Contents', icon: 'document', tone: 'color' },
  search_nodes: { title: 'Library Search', icon: 'folder', tone: 'color' },
  learning_overview: { title: 'Learning Overview', icon: 'grid', tone: 'color' },
  generate_words: { title: 'Prepare Vocabulary', icon: 'dictionary', tone: 'color' },
  get_generations: { title: 'Vocabulary Preparation', icon: 'dictionary', tone: 'color' },
  create_node: { title: 'Library Action', icon: 'plus', tone: 'color' },
  update_node: { title: 'Library Action', icon: 'pencil', tone: 'color' },
  move_nodes: { title: 'Move Nodes', icon: 'pencil', tone: 'color' },
  copy_nodes: { title: 'Copy Nodes', icon: 'document', tone: 'color' },
  delete_nodes: { title: 'Library Action', icon: 'trash', tone: 'color' },
  get_preferences: { title: 'Preferences', icon: 'grid', tone: 'mono' },
  update_preferences: { title: 'Update Preferences', icon: 'grid', tone: 'mono' },
}

export function getToolPreview(toolName: string, args: any, result: any): string {
  const pArgs = safeParse(args);
  const pResult = safeParse(result);

  if (toolName === 'search_words') {
    const q = Array.isArray(pArgs?.queries) ? pArgs.queries.join(', ') : '';
    const hit = Array.isArray(pResult?.items) ? pResult.items[0] : undefined;
    const word = hit?.lemma;
    if (word && word !== q) return `"${q}" → ${word}`;
    return q ? `"${q}"` : '';
  }
  if (toolName === 'learning_overview') {
    const due = pResult?.summaries?.[0]?.due;
    if (due !== undefined) return `${due} due`;
    return '';
  }
  if (toolName === 'search_nodes') {
    const q = Array.isArray(pArgs?.queries) ? pArgs.queries.join(', ') : '';
    const parent = pArgs?.node_id;
    if (q) return `"${q}"`;
    if (parent) return parent;
    return '';
  }
  if (toolName === 'read_library') {
    const name = pResult?.node?.name;
    return name ? `"${name}"` : '';
  }
  if (toolName === 'generate_words') return Array.isArray(pArgs?.words) ? pArgs.words.join(', ') : '';
  if (['create_node', 'update_node', 'move_nodes', 'copy_nodes', 'delete_nodes'].includes(toolName)) {
    const name = pArgs?.name || pResult?.name;
    return name ? `"${name}"` : '';
  }

  if (pArgs && typeof pArgs === 'object') {
    const firstVal = Object.values(pArgs)[0];
    if (typeof firstVal === 'string' || typeof firstVal === 'number') {
      return String(firstVal);
    }
  }
  return '';
}

export function ToolBodyContent({
  toolName,
  args,
  result,
  status,
  isError,
  meta,
}: {
  toolName: string;
  args: any;
  result: any;
  status: { type: string };
  isError?: boolean;
  meta: { title: string };
}) {
  const isRunning = status.type === 'running';

  if (isError) {
    return (
      <div className="p-2 border border-[var(--art-red)] bg-background text-xs text-[var(--art-red)] font-semibold">
        Action could not be completed: {typeof result === 'string' ? result : 'Error executing tool.'}
      </div>
    );
  }
  if (isRunning) {
    return (
      <div className="flex items-center gap-2 p-2 text-xs text-muted-foreground">
        <span className="inline-block size-2 bg-[var(--art-blue)] shimmer" />
        <span className="shimmer text-foreground/70">Querying {meta.title.toLowerCase()}…</span>
      </div>
    );
  }
  if (toolName === 'search_words') {
    return <DictionaryResultView args={args} result={result} />;
  }
  if (toolName === 'learning_overview') {
    const overview = safeParse(result);
    if (!Array.isArray(overview?.summaries)) return <p className="text-xs text-muted-foreground">Progress unavailable.</p>;
    return <><div>{overview.summaries.map((summary: any, index: number) => <section key={summary.node_id ?? index}><ProgressResultView result={summary} /></section>)}</div>{overview?.activity && <p className="text-xs text-muted-foreground">Current streak: {overview.activity.current_streak} days</p>}{overview?.schedules?.map((schedule: any) => <p className="text-xs text-muted-foreground" key={schedule.node_id}>Scope {schedule.node_id}: {schedule.days.reduce((n: number, day: any) => n + day.count, 0)} scheduled reviews ({schedule.start_date}–{schedule.end_date}).</p>)}</>;
  }
  if (toolName === 'search_nodes') {
    return <NodesResultView args={args} result={result} />;
  }
  if (toolName === 'read_library') {
    const page = safeParse(result);
    return <><NodeDetailView result={page} />{page?.senses ? <VocabularyResultView senses={page.senses} /> : <NodesResultView args={args} result={page} />}{page?.next_cursor && <p className="text-xs text-muted-foreground">More results available.</p>}</>;
  }
  if (toolName === 'read_vocabulary') {
    const senses = safeParse(result)?.senses;
    return Array.isArray(senses) ? <VocabularyResultView senses={senses} /> : <p className="text-xs text-muted-foreground">Vocabulary unavailable.</p>;
  }
  if (['generate_words', 'get_generations'].includes(toolName)) {
    const items = safeParse(result)?.items;
    if (!Array.isArray(items)) return <p className="text-xs text-muted-foreground">Vocabulary preparation unavailable.</p>;
    return <div className="ai-tool-content">{items.map((item: any, index: number) => <section key={index} className="py-1.5 text-xs"><strong>{item.lemma ?? item.target ?? 'Word preparation'}</strong><span className="ml-2">{item.status}</span>{item.error && <p className="text-[var(--art-red)]">{item.error}</p>}{item.senses && <VocabularyResultView senses={item.senses} />}</section>)}</div>;
  }
  if (['move_nodes', 'copy_nodes', 'delete_nodes'].includes(toolName)) return <div className="ai-tool-content">{safeParse(result)?.items?.map((item: any, index: number) => <section key={index} className="py-1.5 text-xs"><strong>{item.name ?? `Item ${index + 1}`}</strong><span className="ml-2">{item.status}</span>{item.error && <p className="text-[var(--art-red)]">{item.error}</p>}</section>)}</div>;
  if (['create_node', 'update_node'].includes(toolName)) return <MutationResultView toolName={toolName} args={args} result={result} />;
  return <GenericCleanView args={args} result={result} />;
}

export type CustomToolResultProps = ToolRendererProps & Record<string, any>

export const CustomToolResult: React.FC<CustomToolResultProps> = ({
  toolName,
  args,
  result,
  status,
  isError,
}) => {
  const meta = toolTitles[toolName] ?? {
    title: toolName.replace(/_/g, ' '),
    icon: 'folder',
    tone: 'color',
  }

  const isRunning = status.type === 'running'
  const preview = getToolPreview(toolName, args, result)

  return (
    <details className="ai-tool" open={isRunning}>
      <summary className="ai-tool-summary">
        <Icon name={meta.icon} variant="control" tone={meta.tone} className="size-4 shrink-0" />
        <div className="flex items-baseline gap-2 min-w-0">
          <span className="ai-tool-title">{meta.title}</span>
          {preview && (
            <span className="ai-tool-preview font-mono text-[11px] text-muted-foreground truncate max-w-[180px] hidden sm:inline">
              {preview}
            </span>
          )}
        </div>
        {isRunning && (
          <span className="ai-tool-status" data-running="true">
            Working…
          </span>
        )}
        {isError && (
          <span className="ai-tool-status" data-error="true">
            Failed
          </span>
        )}
        <Icon name="chevron-down" variant="control" className="size-3.5 opacity-60 ml-auto" />
      </summary>
      <div className="ai-tool-body">
        <ToolBodyContent
          toolName={toolName}
          args={args}
          result={result}
          status={status}
          isError={isError}
          meta={meta}
        />
      </div>
    </details>
  )
}
