"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"

import { Badge } from "@/components/ui/badge"
import { CommandGroup, CommandItem } from "@/components/ui/command"
import { Spinner } from "@/components/ui/spinner"
import { toast } from "@/components/ui/toast"
import { searchWords } from "@/lib/actions/words"
import type { SenseContent, WordSearchResult } from "@/lib/api/types"
import { PlusIcon } from "@/lib/icons"

/** Long enough that a fast typist does not fire a request per keystroke. */
const DEBOUNCE_MS = 250

/**
 * Debounced word search.
 *
 * The request is aborted-by-generation rather than by `AbortController`: server
 * actions are not cancellable, so a stale response is discarded on arrival by
 * comparing the generation it was issued under. Without that, a slow response
 * for "ab" can land after a fast one for "abandon" and replace it.
 */
function useWordSearch(query: string) {
  // One piece of state: the results *and* the query they answer. Holding both
  // together is what lets "still loading" and "nothing typed" be derived below
  // rather than set, so the effect never writes state synchronously — which
  // would cascade a second render on every keystroke.
  const [settled, setSettled] = useState<{
    query: string
    results: WordSearchResult[]
  }>({ query: "", results: [] })

  const trimmed = query.trim()

  useEffect(() => {
    const needle = query.trim()
    if (needle.length === 0) return

    let current = true

    const timer = setTimeout(async () => {
      const result = await searchWords(needle)
      if (!current) return
      if (result.success) {
        setSettled({ query: needle, results: result.data })
        return
      }
      // Recording the query on failure too, so the surface stops claiming to be
      // loading something that already came back.
      setSettled({ query: needle, results: [] })
      toast.add({ title: "Search failed", description: result.error })
    }, DEBOUNCE_MS)

    return () => {
      current = false
      clearTimeout(timer)
    }
  }, [query])

  // A stale response for an earlier query is ignored by construction: results
  // are only shown when they answer the query on screen right now.
  const fresh = settled.query === trimmed
  return {
    results: fresh ? settled.results : [],
    loading: trimmed.length > 0 && !fresh,
  }
}

/**
 * The senses a search hit offers, flattened with their headword.
 *
 * `senseId` is non-null here even though the wire type allows null. Every action
 * this list offers — the row key, adding to a deck, opening the detail — needs an
 * id, so a sense without one is dropped rather than rendered as a row that
 * cannot do anything.
 */
interface SenseChoice {
  key: string
  headword: string
  senseId: number
  sense: SenseContent
}

function toSenseChoices(results: WordSearchResult[]): SenseChoice[] {
  return results.flatMap((result) =>
    (result.senses ?? []).flatMap((sense) =>
      sense.senseId == null
        ? []
        : [
            {
              key: `${result.display}-${sense.senseId}`,
              headword: result.display,
              senseId: sense.senseId,
              sense,
            },
          ],
    ),
  )
}

export function PaletteWordResults({
  query,
  targetNodeId,
  onAddSense,
  onNavigate,
}: {
  query: string
  /** Null when the palette was opened without a deck in context. */
  targetNodeId: string | null
  onAddSense: (senseId: number, headword: string) => void
  onNavigate: () => void
}) {
  const router = useRouter()
  const { results, loading } = useWordSearch(query)
  const choices = toSenseChoices(results)

  if (loading) {
    return (
      <div className="flex items-center gap-2 px-3 py-6 text-sm text-muted-foreground">
        <Spinner className="size-4" />
        Searching
      </div>
    )
  }

  if (choices.length === 0) return null

  return (
    <CommandGroup heading="Words">
      {choices.map(({ key, headword, senseId, sense }) => (
        <CommandItem
          key={key}
          value={`${headword} ${sense.definition}`}
          onSelect={() => {
            // With a deck in context the palette adds; without one it opens the
            // sense. Search always exists to put a word somewhere, so adding is
            // the default whenever there is a somewhere.
            if (targetNodeId) {
              onAddSense(senseId, headword)
              return
            }
            onNavigate()
            router.push(`/w/${senseId}`)
          }}
        >
          <span className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="flex items-center gap-2">
              <span className="font-serif font-semibold">{headword}</span>
              <span className="text-xs text-muted-foreground">{sense.pos}</span>
              {sense.cefrLevel ? (
                <Badge variant="outline">{sense.cefrLevel}</Badge>
              ) : null}
            </span>
            <span className="truncate font-serif text-xs text-muted-foreground">
              {sense.definition}
            </span>
          </span>
          {targetNodeId ? <PlusIcon /> : null}
        </CommandItem>
      ))}
    </CommandGroup>
  )
}
