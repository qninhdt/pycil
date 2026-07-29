import { CardsThreeIcon, FolderIcon, LinkSimpleIcon } from "@/lib/icons"
import type { NodeType } from "@/lib/api/types"

/**
 * The glyph for a node kind.
 *
 * A reference gets its own icon rather than the deck icon it points at, because the
 * two behave differently: deleting a reference leaves the target alone, and the
 * target can be revoked out from under it.
 */
export function NodeIcon({ type }: { type: NodeType }) {
  if (type === "FOLDER") return <FolderIcon />
  if (type === "REFERENCE") return <LinkSimpleIcon />
  return <CardsThreeIcon />
}

/** The word for a node kind, for a label or an accessible name. */
export function nodeTypeLabel(type: NodeType): string {
  if (type === "FOLDER") return "Folder"
  if (type === "REFERENCE") return "Reference"
  return "Deck"
}
