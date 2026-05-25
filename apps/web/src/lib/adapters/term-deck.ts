import type { NodeRead } from "@/types/domain";
import type { TermDeck } from "@/types/deck";

export function nodeToTermDeck(node: NodeRead): TermDeck {
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
  };
}

export function nodesToTermDecks(nodes: NodeRead[]): TermDeck[] {
  return nodes.map(nodeToTermDeck);
}
