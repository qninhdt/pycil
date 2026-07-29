import { Fragment } from "react"
import Link from "next/link"

import {
  Breadcrumb,
  BreadcrumbEllipsis,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import type { NodeAncestor } from "@/lib/api/types"

/**
 * The trail from the library root to the node on screen.
 *
 * The chain comes from the node read itself, so this costs no extra request.
 *
 * A truncated chain is the case worth care. The API returns only the ancestors the
 * caller may read, so a public deck inside a private folder arrives with its parent
 * missing. Rendering that as a short trail would claim the deck sits at the root,
 * which is wrong and misleads about where a shared link points. An ellipsis stands in
 * for the hidden part: something is above this, and you cannot see it.
 */
export function NodeBreadcrumb({
  path,
  current,
  hasHiddenAncestors = false,
}: {
  /** Root-first ancestors, excluding the current node. */
  path: NodeAncestor[]
  current: string
  /**
   * Whether ancestors exist that this caller cannot read.
   *
   * Passed in rather than inferred. An empty path means "at the root" for an owner
   * and "everything above was filtered" for a visitor, and only the caller knows
   * which — it holds the node's `parentNodeId`, which is the difference.
   */
  hasHiddenAncestors?: boolean
}) {
  return (
    <Breadcrumb>
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink render={<Link href="/library" />}>Library</BreadcrumbLink>
        </BreadcrumbItem>

        {hasHiddenAncestors ? (
          <>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbEllipsis />
            </BreadcrumbItem>
          </>
        ) : null}

        {path.map((ancestor) => (
          // Fragment rather than an element: `BreadcrumbList` is an `<ol>`, and both
          // children here are `<li>`, so any wrapper would be invalid markup.
          <Fragment key={ancestor.id}>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbLink render={<Link href={`/library/${ancestor.id}`} />}>
                {ancestor.name}
              </BreadcrumbLink>
            </BreadcrumbItem>
          </Fragment>
        ))}

        <BreadcrumbSeparator />
        <BreadcrumbItem>
          <BreadcrumbPage>{current}</BreadcrumbPage>
        </BreadcrumbItem>
      </BreadcrumbList>
    </Breadcrumb>
  )
}
