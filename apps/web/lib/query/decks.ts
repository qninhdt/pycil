import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { SenseItem } from "@/lib/api/types";
import { queryKeys } from "./keys";

async function fetchDeckItems(deckId: string): Promise<SenseItem[]> {
  const res = await fetch(`/api/decks/${deckId}/items`);
  if (!res.ok) {
    throw new Error("Failed to fetch deck items");
  }
  return res.json();
}

export function useDeckItems(deckId: string) {
  return useQuery({
    queryKey: queryKeys.decks.items(deckId),
    queryFn: () => fetchDeckItems(deckId),
    enabled: !!deckId,
  });
}

export function useRemoveSenseFromDeck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ deckId, senseId }: { deckId: string; senseId: number }): Promise<void> => {
      const res = await fetch(`/api/decks/${deckId}/senses/${senseId}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error?.error?.message || "Failed to remove word from deck");
      }
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.decks.items(variables.deckId),
      });
    },
  });
}
