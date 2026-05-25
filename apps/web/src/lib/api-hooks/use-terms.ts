"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import * as termsApi from "@/lib/api-client/terms";
import { queryKeys } from "@/lib/api-client/query-keys";
import type { UUID } from "@/types/domain";

export function useDeckTerms(deckId: UUID | undefined) {
  return useQuery({
    queryKey: deckId
      ? queryKeys.deck.terms(deckId)
      : queryKeys.deck.terms("__none"),
    queryFn: () => termsApi.listDeckTerms(deckId as UUID),
    enabled: !!deckId,
  });
}

export function useAddTerm(deckId: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (value: string) => termsApi.addTerm(deckId, value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.deck.terms(deckId) });
      qc.invalidateQueries({ queryKey: queryKeys.nodes.detail(deckId) });
    },
  });
}
