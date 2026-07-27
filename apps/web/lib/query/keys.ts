export const queryKeys = {
  me: ["me"] as const,
  capabilities: ["capabilities"] as const,
  nodes: {
    all: ["nodes"] as const,
    list: (parentId?: string) => ["nodes", "list", parentId] as const,
    detail: (id: string) => ["nodes", "detail", id] as const,
  },
  decks: {
    items: (deckId: string) => ["decks", deckId, "items"] as const,
    settings: (deckId: string) => ["decks", deckId, "settings"] as const,
  },
  folders: {
    items: (folderId: string, offset?: number) => ["folders", folderId, "items", offset] as const,
    weakest: (folderId: string) => ["folders", folderId, "weakest"] as const,
    cefr: (folderId: string) => ["folders", folderId, "cefr"] as const,
    history: (folderId: string) => ["folders", folderId, "history"] as const,
  },
  sessions: {
    detail: (id: string) => ["sessions", id] as const,
    next: (id: string) => ["sessions", id, "next"] as const,
  },
  search: (q: string) => ["words", "search", q] as const,
  userDecks: ["user-decks"] as const,
};
