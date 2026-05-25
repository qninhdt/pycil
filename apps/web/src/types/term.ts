export interface TermDefinition {
  id: string;
  definition: string;
  language?: string;
  partOfSpeech?: string;
  example?: string;
}

export interface SearchableTerm {
  id: string;
  term: string;
  definitions: TermDefinition[];
  isGenerating?: boolean; // True when LLM is generating definitions
  generatedAt?: string; // Timestamp when definitions were generated
}

export interface DeckTerm {
  id: string;
  term: string;
  definition: string;
  mastered: boolean;
  difficulty: "easy" | "medium" | "hard";
  addedAt?: string; // Timestamp when added to deck
  isRecentlyAdded?: boolean; // For highlighting
}

export interface AddTermRequest {
  termId: string;
  selectedDefinitions: string[]; // Array of definition IDs
}

export interface Term {
  id: string;
  term: string;
  definition: string;
  mastered: boolean;
  difficulty: "easy" | "medium" | "hard";
  addedAt?: string; // Timestamp when added to deck
  isRecentlyAdded?: boolean; // For highlighting
}
