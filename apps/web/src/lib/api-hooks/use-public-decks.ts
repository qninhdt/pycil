"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import * as publicDecksApi from "@/lib/api-client/public-decks";
import { queryKeys } from "@/lib/api-client/query-keys";

export function usePublicDecks(q = "") {
  return useQuery({
    queryKey: queryKeys.publicDecks.list(q),
    queryFn: () => publicDecksApi.listPublicDecks(q || undefined),
  });
}

export function useClonePublicDeck() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (deckId: string) => publicDecksApi.clonePublicDeck(deckId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.nodes.all() });
    },
    onError: (err) =>
      toast.error(err instanceof Error ? err.message : "Clone failed"),
  });
}
