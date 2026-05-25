"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as learningApi from "@/lib/api-client/learning";
import { queryKeys } from "@/lib/api-client/query-keys";
import type {
  StartSessionRequest,
  SubmitAnswerRequest,
  UUID,
} from "@/types/domain";

export function useStartSession(deckId: UUID) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: StartSessionRequest = {}) =>
      learningApi.startSession(deckId, body),
    onSuccess: (resp) => {
      qc.invalidateQueries({ queryKey: queryKeys.session.detail(resp.session_id) });
    },
  });
}

export function useSessionQuestion(sessionId: string | null | undefined) {
  return useQuery({
    queryKey: sessionId
      ? queryKeys.session.question(sessionId)
      : queryKeys.session.question("__none"),
    queryFn: () => learningApi.getSessionQuestion(sessionId as string),
    enabled: !!sessionId,
  });
}

export function useSubmitAnswer(sessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SubmitAnswerRequest) =>
      learningApi.submitAnswer(sessionId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.session.question(sessionId) });
    },
  });
}
