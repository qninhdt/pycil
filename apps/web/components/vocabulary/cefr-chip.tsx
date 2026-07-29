import { Badge } from "@/components/ui/badge"

/**
 * The CEFR level and the content tier, as small outline chips.
 *
 * Both are open strings on the wire rather than enums: the levels present depend on
 * the data Lexi holds, and a tier vocabulary can grow upstream without this app
 * shipping. So neither is mapped to a fixed palette — an unknown value must render
 * as itself rather than fall through to a default colour that means something else.
 */
export function CefrChip({ level }: { level?: string | null }) {
  if (!level) return null
  return (
    <Badge variant="outline" title={`CEFR level ${level}`}>
      {level}
    </Badge>
  )
}

/**
 * How the sense was sourced upstream.
 *
 * Rendered lower-contrast than CEFR on purpose: it is provenance, useful when
 * present and never the reason a learner is looking at the word.
 */
export function TierChip({ tier }: { tier?: string | null }) {
  if (!tier) return null
  return (
    <Badge variant="ghost" className="text-muted-foreground">
      {tier}
    </Badge>
  )
}
