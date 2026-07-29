"use client"

import { useRouter, useSearchParams } from "next/navigation"

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { NodeRead } from "@/lib/api/types"

/**
 * Points the whole screen at everything, or at one folder.
 *
 * Only folders are offered, because folder scope is the only scope the analytics
 * endpoints accept: a deck has `/decks/{id}/items` but no stats, weakest, cefr or
 * history of its own. Offering a deck here would build a request the API answers
 * with a 404.
 *
 * Roots only, one level deep. A nested picker would be a third node browser after
 * the palette and the move dialog, and the useful question on this screen is which
 * broad area to look at rather than which exact subfolder.
 *
 * The scope lives in the URL rather than in state so the view is linkable and a
 * reload keeps it, and so the page can stay a server component that reads whatever
 * the parameter says.
 */
export function ScopeSelector({ folders, nodeId }: { folders: NodeRead[]; nodeId: string | null }) {
  const router = useRouter()
  const searchParams = useSearchParams()

  // The primitive can report a cleared selection as null. There is no "no scope" to
  // render, so a null is read as global rather than left to build a request with an
  // undefined node id.
  function select(value: string | null) {
    const params = new URLSearchParams(searchParams)
    if (value === null || value === GLOBAL) {
      params.delete("node")
    } else {
      params.set("node", value)
    }
    // Switching scope replaces the whole page, so returning to the top is right
    // here — unlike the range control, which sits beside the chart it changes.
    router.push(params.size > 0 ? `?${params.toString()}` : "/progress")
  }

  // Nothing to switch between: a learner with no folders would get a control whose
  // only option is the one already selected.
  if (folders.length === 0) return null

  return (
    <Select value={nodeId ?? GLOBAL} onValueChange={select}>
      <SelectTrigger className="w-full sm:w-64" aria-label="Scope">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectGroup>
          <SelectItem value={GLOBAL}>Everything</SelectItem>
          {folders.map((folder) => (
            <SelectItem key={folder.id} value={folder.id}>
              {folder.name}
            </SelectItem>
          ))}
        </SelectGroup>
      </SelectContent>
    </Select>
  )
}

/**
 * The sentinel for global scope.
 *
 * A select needs a non-empty value for every option, and the global case has no node
 * id by definition. It is translated back to an absent `node` parameter above, so the
 * sentinel never reaches a URL or a request.
 */
const GLOBAL = "all"
