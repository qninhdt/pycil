/**
 * The word itself.
 *
 * SERIF RULE: this component and `DefinitionBlock` are the only two places in the
 * product permitted to use the serif face. Everything else — labels, buttons,
 * counts, navigation — is the sans face. The serif is what separates the
 * dictionary content from the interface around it, and that distinction stops
 * meaning anything the moment a third component borrows it.
 */

import { cn } from "@/lib/utils"

/**
 * A sense can outlive its headword: the upstream dictionary can regenerate a word
 * away while the learner's own state for it survives, so the API keeps serving the
 * row with `word: null`. Rendering an empty heading in that case leaves a row that
 * looks broken, so the fallback names the situation instead.
 */
export function Headword({
  word,
  className,
  as: Tag = "span",
}: {
  word?: string | null
  className?: string
  as?: "h1" | "h2" | "h3" | "span"
}) {
  if (!word) {
    return (
      <Tag className={cn("text-muted-foreground italic", className)}>
        Word no longer available
      </Tag>
    )
  }

  return (
    <Tag className={cn("font-serif tracking-tight", className)}>{word}</Tag>
  )
}
