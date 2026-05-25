"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as questionsApi from "@/lib/api-client/questions";
import { queryKeys } from "@/lib/api-client/query-keys";

export function useQuestionForDefinition(definitionId: number | undefined) {
  return useQuery({
    queryKey:
      definitionId !== undefined
        ? queryKeys.question.forDefinition(definitionId)
        : queryKeys.question.forDefinition(-1),
    queryFn: () => questionsApi.fetchOrEnqueueQuestion(definitionId as number),
    enabled: definitionId !== undefined,
  });
}

export function useCheckAnswer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { questionId: string; selectedIndex: number }) =>
      questionsApi.checkAnswer(vars.questionId, vars.selectedIndex),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["question"] });
    },
  });
}
