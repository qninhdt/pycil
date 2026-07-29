import { cn } from "@/lib/utils"

/**
 * British and American pronunciation, as text.
 *
 * Text only. There is no audio in this product, so a speaker affordance here would
 * promise something that does not exist.
 *
 * The mono face is deliberate: IPA in a proportional face has uneven spacing around
 * the narrow glyphs, and the fallback chain behind `--font-mono` was extended
 * specifically so extended IPA renders rather than showing tofu.
 */
export function IpaLine({
  ipaUk,
  ipaUs,
  className,
}: {
  ipaUk?: string | null
  ipaUs?: string | null
  className?: string
}) {
  // Nothing to show is nothing rendered, not an empty row with two labels.
  if (!ipaUk && !ipaUs) return null

  return (
    <dl className={cn("flex flex-wrap items-baseline gap-x-4 gap-y-1", className)}>
      {ipaUk ? (
        <div className="flex items-baseline gap-1.5">
          <dt className="text-xs tracking-wide text-muted-foreground uppercase">UK</dt>
          <dd className="font-mono text-sm">{ipaUk}</dd>
        </div>
      ) : null}
      {ipaUs ? (
        <div className="flex items-baseline gap-1.5">
          <dt className="text-xs tracking-wide text-muted-foreground uppercase">US</dt>
          <dd className="font-mono text-sm">{ipaUs}</dd>
        </div>
      ) : null}
    </dl>
  )
}
