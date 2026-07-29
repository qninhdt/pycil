/**
 * A sense's definition.
 *
 * SERIF RULE: this component and `Headword` are the only two places in the product
 * permitted to use the serif face. See the note in `headword.tsx` for why that
 * boundary matters.
 */

import { cn } from "@/lib/utils"

/**
 * `guideword` is Cambridge's short disambiguator for a sense — the parenthetical
 * that tells you which "run" you are reading. It sits above the definition because
 * it is what a reader scans when a word has eight senses.
 */
export function DefinitionBlock({
  definition,
  guideword,
  className,
}: {
  definition: string
  guideword?: string | null
  className?: string
}) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      {guideword ? (
        <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          {guideword}
        </span>
      ) : null}
      <p className="font-serif leading-relaxed">{definition}</p>
    </div>
  )
}
