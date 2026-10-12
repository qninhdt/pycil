import { Fragment } from 'react'
import { parseMarkedText } from '@/lib/marked-text'

/** Render the backend's target protocol, never HTML or a guessed headword match. */
export function MarkedText({ text, className }: { text: string; className?: string }) {
  const parsed = parseMarkedText(text)
  return <span className={className} data-markup={parsed.valid ? 'valid' : 'invalid'}>{parsed.spans.map((span, index) => {
    const prefix = parsed.text.slice(parsed.spans[index - 1]?.end ?? 0, span.start)
    return <Fragment key={span.start}>{prefix}<mark className="inline font-bold text-[color-mix(in_srgb,var(--palette-blue-dark)_75%,var(--palette-ink))] dark:text-[color-mix(in_srgb,var(--art-blue)_80%,var(--palette-canvas))] bg-[color-mix(in_srgb,var(--art-blue)_12%,transparent)] dark:bg-[color-mix(in_srgb,var(--art-blue)_22%,transparent)] px-1 py-0.5 rounded-none underline decoration-art-blue/40 dark:decoration-art-blue/60 underline-offset-[3px] decoration-1 box-decoration-clone forced-colors:text-[Highlight] forced-colors:underline" data-inf={span.inf}>{span.surface}</mark></Fragment>
  })}{parsed.text.slice(parsed.spans.at(-1)?.end ?? 0)}</span>
}
