/** Server actions for the question API. */
"use server";

import { checkAnswer } from "@/lib/questions";
import type { QuestionCheckResponse } from "@/lib/types";

export async function checkAnswerAction(
  questionId: string,
  selectedIndex: number
): Promise<QuestionCheckResponse> {
  return checkAnswer(questionId, selectedIndex);
}
