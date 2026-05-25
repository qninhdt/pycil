export interface StudyProgressData {
  newCards: number;
  stillLearning: number;
  almostDone: number;
  mastered: number;
}

export interface TermDeck {
  id: string;
  title: string;
  description: string;
  cardCount: number;
  updatedAt: string;
  createdAt: string;
  isFolder?: boolean;
  masteryProgress: number;
  studyTime: number;
  tags: string[];
  author?: string;
  deckCount?: number; // for folders
  folderId?: string; // for decks that belong to a folder
  isShortcut?: boolean; // for shortcuts
  targetId?: string; // ID of the target deck/folder/collection
  targetType?: "deck" | "folder"; // type of target
  isPinned?: boolean; // for pinned items
}

export interface StudySession {
  id: string;
  deckId: string;
  mode: "learn" | "practice" | "spaced-repetition";
  progress: number;
  totalCards: number;
  correctAnswers: number;
  timeSpent: number;
  completedAt?: string;
}
