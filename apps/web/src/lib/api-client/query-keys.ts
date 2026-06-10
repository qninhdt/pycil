import type { UUID } from "@/types/domain";

export const queryKeys = {
  me: () => ["me"] as const,

  nodes: {
    all: () => ["nodes"] as const,
    root: () => ["nodes", "root"] as const,
    detail: (id: UUID) => ["nodes", id] as const,
    children: (id: UUID) => ["nodes", id, "children"] as const,
  },

  deck: {
    terms: (id: UUID) => ["deck", id, "terms"] as const,
  },

  job: (id: string) => ["job", id] as const,

  question: {
    forDefinition: (definitionId: number) =>
      ["question", "definition", definitionId] as const,
  },

  session: {
    detail: (id: string) => ["session", id] as const,
    question: (id: string) => ["session", id, "question"] as const,
  },

  admin: {
    users: (q?: string) => ["admin", "users", q ?? ""] as const,
    userDetail: (id: string) => ["admin", "users", id] as const,
    metrics: (days: number) => ["admin", "metrics", days] as const,
    reports: (status: string) => ["admin", "reports", status] as const,
    flags: () => ["admin", "flags"] as const,
    health: () => ["admin", "health"] as const,
    audit: (filters: string) => ["admin", "audit", filters] as const,
  },
} as const;

export type QueryKeys = typeof queryKeys;
