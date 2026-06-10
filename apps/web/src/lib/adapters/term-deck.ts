import type { NodeRead } from "@/types/domain";
import type { TermDeck } from "@/types/deck";

export function nodeToTermDeck(node: NodeRead): TermDeck {
  const isShortcut = node.type === "SHORTCUT";
  return {
    id: node.id,
    title: node.name,
    description: node.description ?? "",
    cardCount: node.definition_count,
    updatedAt: node.updated_at,
    createdAt: node.created_at,
    isFolder: node.type === "FOLDER",
    masteryProgress: 0,
    studyTime: 0,
    tags: [],
    folderId: node.parent_node_id ?? undefined,
    isPinned: node.is_pinned,
    isShortcut,
    // The target's concrete type is not on NodeRead (only its id), so the
    // shortcut row links by id and the destination route resolves the type.
    targetId: node.target_node_id ?? undefined,
  };
}

export function nodesToTermDecks(nodes: NodeRead[]): TermDeck[] {
  return nodes.map(nodeToTermDeck);
}
