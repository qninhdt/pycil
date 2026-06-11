"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as learningApi from "@/lib/api-client/learning";
import { queryKeys } from "@/lib/api-client/query-keys";
import type {
  ApplyVerdictRequest,
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
    // Cold-start generation: the first next_question returns status "pending"
    // while the worker generates the MCQ on demand (no prewarmed bank entry).
    // Without polling, the query never re-fetches and the session UI hangs on
    // the loading skeleton forever. Poll while pending; stop once ready /
    // session_complete.
    refetchInterval: (query) =>
      query.state.data?.status === "pending" ? 1500 : false,
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

export function useApplyVerdict(sessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ApplyVerdictRequest) =>
      learningApi.applyVerdict(sessionId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.session.question(sessionId) });
    },
  });
}
