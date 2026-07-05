export interface Question {
  id: string;
  // Opaque lexi sense id behind this question. Optional: the post-answer
  // reconstruction path does not carry it.
  senseId?: number;
  type: string;
  term: string;
  definition: string;
  options?: string[]; // For multiple choice questions
  correctAnswer: string;
  userAnswer?: string;
  isCorrect?: boolean;
  skipped?: boolean;
  timeSpent?: number;
  // Post-submit reveal: per-option rationale (MCQ) + generic grading feedback.
  distractorRationale?: string[];
  feedback?: string;
  score?: number;
}

export interface LearningRound {
  id: string;
  roundNumber: number;
  questions: Question[];
  currentQuestionIndex: number;
  correctAnswers: number;
  isCompleted: boolean;
  startTime: Date;
  endTime?: Date;
}

export interface LearningSession {
  id: string;
  deckId: string;
  rounds: LearningRound[];
  currentRoundIndex: number;
  totalReviewedWords: number;
  targetWordsCount: number;
  isCompleted: boolean;
  startTime: Date;
  endTime?: Date;
}

export interface LearningProgress {
  totalReviewedWords: number;
  targetWordsCount: number;
  currentRoundProgress: number;
  totalRoundsProgress: number;
  currentRound: number;
  totalRounds: number;
}
