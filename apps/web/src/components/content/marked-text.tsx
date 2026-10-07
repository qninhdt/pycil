import { Fragment } from 'react'
import { parseMarkedText } from '@/lib/marked-text'

/** Render the backend's target protocol, never HTML or a guessed headword match. */
export function MarkedText({ text }: { text: string }) {
  const parsed = parseMarkedText(text)
  return <span data-markup={parsed.valid ? 'valid' : 'invalid'}>{parsed.spans.map((span, index) => {
    const prefix = parsed.text.slice(parsed.spans[index - 1]?.end ?? 0, span.start)
    return <Fragment key={span.start}>{prefix}<mark className="bg-transparent font-extrabold text-[color-mix(in_srgb,var(--palette-blue-dark)_70%,var(--palette-ink))] dark:text-[color-mix(in_srgb,var(--art-blue)_65%,var(--palette-canvas))] forced-colors:text-[Highlight] forced-colors:underline" data-inf={span.inf}>{span.surface}</mark></Fragment>
  })}{parsed.text.slice(parsed.spans.at(-1)?.end ?? 0)}</span>
}
