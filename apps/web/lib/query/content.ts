import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addSenseToDeck, searchWords, submitWordGeneration } from "@/lib/actions/content";
import { queryKeys } from "@/lib/query/keys";
import type { NodeItem, NodePageResponse } from "@/lib/api/types";

export function useWordSearch(query: string) {
  const cleanQuery = query.trim();
  return useQuery({
    queryKey: queryKeys.search(cleanQuery),
    queryFn: () => searchWords(cleanQuery),
    enabled: cleanQuery.length > 0,
    staleTime: 1000 * 60 * 5, // 5 minutes cache for dictionary search
  });
}

export function useSubmitWordGeneration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (wordQuery: string) => submitWordGeneration(wordQuery),
    onSuccess: (_, wordQuery) => {
      // Invalidate existing search cache for the word query when job starts
      queryClient.invalidateQueries({ queryKey: queryKeys.search(wordQuery.trim()) });
    },
  });
}

export function useUserDecks() {
  return useQuery({
    queryKey: queryKeys.userDecks,
    queryFn: async () => {
      const res = await fetch("/api/nodes?limit=100", { cache: "no-store" });
      if (!res.ok) return [];
      const data: NodePageResponse = await res.json();
      const items: NodeItem[] = data.items || [];
      return items.filter((item) => item.type === "DECK");
    },
    staleTime: 1000 * 60 * 2,
  });
}

export function useAddSenseToDeck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ nodeId, senseId }: { nodeId: string; senseId: number }) =>
      addSenseToDeck(nodeId, senseId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.decks.items(variables.nodeId) });
    },
  });
}
