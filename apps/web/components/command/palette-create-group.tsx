"use client"

import { useState } from "react"

import { CommandGroup, CommandItem } from "@/components/ui/command"
import { Spinner } from "@/components/ui/spinner"
import { toast } from "@/components/ui/toast"
import { generateWord } from "@/lib/actions/words"
import { SparkleIcon } from "@/lib/icons"
import { useActivityActions } from "@/lib/stores/store-provider"

/**
 * The escape hatch when the dictionary does not have the word yet.
 *
 * Generation is asynchronous and can outlive this palette, so the returned task
 * id is registered with the activity store before anything else happens. That
 * registration is what makes the result reachable after the palette closes, and
 * after a reload.
 */
export function PaletteCreateGroup({
  query,
  onSubmitted,
}: {
  query: string
  onSubmitted: () => void
}) {
  const { register } = useActivityActions()
  const [submitting, setSubmitting] = useState(false)
  const trimmed = query.trim()

  if (trimmed.length === 0) return null

  const onSelect = async () => {
    if (submitting) return
    setSubmitting(true)
    const result = await generateWord(trimmed)
    setSubmitting(false)

    if (!result.success) {
      toast.add({ title: "Could not start", description: result.error })
      return
    }

    register({
      taskId: result.data.taskId,
      kind: "word-generation",
      // The query is the only name this work has until it finishes, so the
      // activity row would otherwise be an anonymous spinner.
      label: trimmed,
    })
    toast.add({
      title: "Adding the word",
      description: "It will appear in Activity when it is ready.",
    })
    onSubmitted()
  }

  return (
    <CommandGroup heading="Not found">
      {/* `value` includes the query so cmdk keeps this item visible while the
          learner is still typing the thing they want generated. */}
      <CommandItem value={`generate ${trimmed}`} onSelect={onSelect}>
        {submitting ? <Spinner className="size-4" /> : <SparkleIcon />}
        <span className="min-w-0 flex-1 truncate">
          Add <span className="font-serif font-semibold">{trimmed}</span> to the
          dictionary
        </span>
      </CommandItem>
    </CommandGroup>
  )
}
