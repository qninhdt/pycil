"use client"

/**
 * What the assistant did, not just what it said.
 *
 * Collapsed by default because a tool call is supporting evidence: the learner
 * usually wants the answer, and only sometimes wants to check where it came from.
 * Hiding it entirely would be worse — this is an agent acting on their library, so
 * "which of my decks did you read" has to be answerable.
 */

import * as React from "react"

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import { Spinner } from "@/components/ui/spinner"
import { CaretDownIcon, WrenchIcon } from "@/lib/icons"
import { cn } from "@/lib/utils"

import type { ToolTurn } from "@/lib/assistant/transcript"

/** `search_word` reads as "Search word", which is what a person would call it. */
function readableTool(tool: string): string {
  const spaced = tool.replace(/_/g, " ")
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function ToolCallTrace({ turn }: { turn: ToolTurn }) {
  const [open, setOpen] = React.useState(false)
  const pending = turn.result === null

  // Nothing to expand while the call is outstanding, so it renders as a plain
  // marker rather than a trigger that opens an empty panel.
  if (pending) {
    return (
      <Marker>
        <MarkerIcon>
          <Spinner />
        </MarkerIcon>
        <MarkerContent>{readableTool(turn.tool)}…</MarkerContent>
      </Marker>
    )
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger
        className={cn(
          "group/tool flex min-h-9 w-full items-center gap-2 rounded-md px-1 text-left",
          "text-sm text-muted-foreground outline-none",
          "hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring",
        )}
      >
        <WrenchIcon aria-hidden className="size-4 shrink-0" />
        <span className="min-w-0 flex-1 truncate">{readableTool(turn.tool)}</span>
        <CaretDownIcon
          aria-hidden
          className="size-4 shrink-0 transition-transform group-data-[panel-open]/tool:rotate-180"
        />
      </CollapsibleTrigger>

      <CollapsibleContent>
        {/* Presented as an excerpt because it is one: the API truncates every tool
            result to 1000 characters before persisting it, so implying this is the
            whole output would be a lie the UI tells on the server's behalf. */}
        <figure className="mt-1 flex flex-col gap-1 px-1">
          <pre className="max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap">
            {turn.result}
          </pre>
          <figcaption className="text-xs text-muted-foreground">
            Excerpt, up to the first 1000 characters.
          </figcaption>
        </figure>
      </CollapsibleContent>
    </Collapsible>
  )
}
