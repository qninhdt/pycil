import { SearchableTerm } from "@/types/term";
import type { User, TermDeck, StudySession, Term } from "@/types";

// Mock Data
export const mockUser: User = {
  id: "1",
  name: "Alex Johnson",
  username: "alexj_study",
  email: "alex.johnson@email.com",
  avatar:
    "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=150&h=150&fit=crop&crop=face",
  coverImage:
    "https://images.unsplash.com/photo-1557683316-973673baf926?w=800&h=200&fit=crop",
  followers: 1247,
  following: 589,
  level: 12,
  streak: 15,
  coins: 2480,
  referralCoins: 85,
  referralLink: "https://pycil.app/ref/alexj_study",
  badges: [
    {
      id: "1",
      name: "First Steps",
      icon: "🎯",
      description: "Complete your first study session",
    },
    {
      id: "2",
      name: "Week Warrior",
      icon: "🔥",
      description: "Study for 7 days straight",
    },
    {
      id: "3",
      name: "Term Master",
      icon: "⚡",
      description: "Create 100 terms",
    },
    {
      id: "4",
      name: "Night Owl",
      icon: "🦉",
      description: "Study past midnight",
    },
  ],
};

export const mockTermDecks: TermDeck[] = [
  {
    id: "folder-1",
    title: "HAIRY POTTER",
    description: "Harry Potter themed term collection",
    cardCount: 0,
    updatedAt: "2h ago",
    createdAt: "2024-08-10",
    isFolder: true,
    masteryProgress: 65,
    studyTime: 320,
    tags: ["fantasy", "books"],
    author: "You",
    deckCount: 5,
    isPinned: true,
  },
  {
    id: "1",
    title: "English Vocabulary - Advanced",
    description:
      "Advanced English vocabulary for academic and professional use",
    cardCount: 114,
    updatedAt: "3h ago",
    createdAt: "2024-08-15",
    masteryProgress: 0,
    studyTime: 240,
    tags: ["english", "vocabulary", "advanced"],
    author: "You",
    folderId: "folder-1",
  },
  {
    id: "2",
    title: "Magical Creatures",
    description: "Fantastic beasts and magical creatures from the HP universe",
    cardCount: 32,
    updatedAt: "5h ago",
    createdAt: "2024-08-14",
    masteryProgress: 92,
    studyTime: 180,
    tags: ["creatures", "magical beasts"],
    author: "You",
    folderId: "folder-1",
    isPinned: true,
  },
  {
    id: "3",
    title: "Hogwarts Houses and Characters",
    description: "Important characters and their house affiliations",
    cardCount: 28,
    updatedAt: "1 day ago",
    createdAt: "2024-08-12",
    masteryProgress: 85,
    studyTime: 150,
    tags: ["characters", "houses", "hogwarts"],
    author: "You",
    folderId: "folder-1",
  },
  {
    id: "4",
    title: "Terms (4)",
    description:
      "Comprehensive study of cellular components and their functions",
    cardCount: 4,
    updatedAt: "5h ago",
    createdAt: "2024-08-15",
    masteryProgress: 78,
    studyTime: 240,
    tags: ["biology", "cells", "advanced"],
    author: "You",
  },
  {
    id: "5",
    title: "AP Chemistry Notes",
    description: "Complete AP Chemistry curriculum materials",
    cardCount: 267,
    updatedAt: "1 hour ago",
    createdAt: "2024-08-10",
    masteryProgress: 45,
    studyTime: 520,
    tags: ["chemistry", "ap", "exam-prep"],
    author: "You",
    isPinned: true,
  },
  {
    id: "7",
    title: "Spanish Vocabulary - Intermediate",
    description: "Essential vocabulary for intermediate Spanish learners",
    cardCount: 89,
    updatedAt: "3 hours ago",
    createdAt: "2024-08-20",
    masteryProgress: 92,
    studyTime: 180,
    tags: ["spanish", "vocabulary", "intermediate"],
    author: "You",
  },
  {
    id: "8",
    title: "World History - Renaissance",
    description:
      "Key figures, events, and concepts from the Renaissance period",
    cardCount: 156,
    updatedAt: "1 day ago",
    createdAt: "2024-08-05",
    masteryProgress: 34,
    studyTime: 320,
    tags: ["history", "renaissance", "europe"],
    author: "You",
  },
  {
    id: "9",
    title: "Physics - Quantum Mechanics",
    description: "Fundamental principles of quantum physics",
    cardCount: 78,
    updatedAt: "2 days ago",
    createdAt: "2024-07-28",
    masteryProgress: 67,
    studyTime: 290,
    tags: ["physics", "quantum", "advanced"],
  },
  {
    id: "6",
    title: "Computer Science - Algorithms",
    description: "Common algorithms and data structures",
    cardCount: 203,
    updatedAt: "3 days ago",
    createdAt: "2024-07-20",
    masteryProgress: 88,
    studyTime: 450,
    tags: ["computer-science", "algorithms", "programming"],
  },
  // Shortcuts
  {
    id: "shortcut-1",
    title: "Shortcut to AP Chemistry Notes",
    description: "Quick access to chemistry study materials",
    cardCount: 267, // inherited from target
    updatedAt: "1 hour ago",
    createdAt: "2024-08-25",
    masteryProgress: 45, // inherited from target
    studyTime: 520, // inherited from target
    tags: ["chemistry", "ap", "exam-prep", "shortcut"],
    author: "You",
    isShortcut: true,
    targetId: "5",
    targetType: "deck",
    isPinned: true,
  },
  {
    id: "shortcut-2",
    title: "Shortcut to Harry Potter Collection",
    description: "Quick access to all Harry Potter materials",
    cardCount: 0, // folders don't have cards directly
    updatedAt: "2h ago",
    createdAt: "2024-08-26",
    masteryProgress: 65,
    studyTime: 320,
    tags: ["fantasy", "books", "collection", "shortcut"],
    author: "You",
    isShortcut: true,
    targetId: "folder-1",
    targetType: "folder",
  },
];

export const mockTerms: Record<string, Term[]> = {
  "1": [
    {
      id: "card_1_1",
      term: "ruddy",
      definition: "a. hồng hào, khỏe mạnh",
      mastered: false,
      difficulty: "medium",
    },
    {
      id: "card_1_2",
      term: "pace yourself",
      definition:
        "cần thận không làm việc gì quá nhanh, cần thận không làm việc gì quá nhanh, cần thận không làm việc gì quá nhanh, cần thận không làm việc gì quá nhanh, cần thận không làm việc gì quá nhanh, cần thận không làm việc gì quá nhanh",
      mastered: false,
      difficulty: "medium",
    },
    {
      id: "card_1_3",
      term: "set off",
      definition: "khởi hành, bắt đầu lên đường",
      mastered: false,
      difficulty: "medium",
    },
    {
      id: "card_1_4",
      term: "trolley",
      definition: "n. xe đẩy",
      mastered: false,
      difficulty: "easy",
    },
    {
      id: "card_1_5",
      term: "plump",
      definition: "v. làm đầy, phình ra",
      mastered: false,
      difficulty: "medium",
    },
    {
      id: "card_1_6",
      term: "serendipity",
      definition:
        "the occurrence and development of events by chance in a happy or beneficial way",
      mastered: false,
      difficulty: "medium",
      addedAt: "2024-08-31T10:30:00Z",
      isRecentlyAdded: true,
    },
    {
      id: "card_1_7",
      term: "ephemeral",
      definition: "lasting for a very short time",
      mastered: false,
      difficulty: "easy",
      addedAt: "2024-08-31T10:25:00Z",
      isRecentlyAdded: true,
    },
    // Additional cards to reach 114 total (showing first 7)
    ...Array.from({ length: 107 }, (_, i) => ({
      id: `card_1_${i + 8}`,
      term: `term_${i + 8}`,
      definition: `definition_${i + 8}`,
      mastered: false,
      difficulty: "medium" as const,
    })),
  ],
};

export const mockStudySessions: StudySession[] = [
  {
    id: "session_1",
    deckId: "1",
    mode: "learn",
    progress: 70,
    totalCards: 114,
    correctAnswers: 80,
    timeSpent: 25,
    completedAt: "2024-08-30T10:30:00Z",
  },
  {
    id: "session_2",
    deckId: "1",
    mode: "practice",
    progress: 85,
    totalCards: 114,
    correctAnswers: 97,
    timeSpent: 18,
    completedAt: "2024-08-29T14:15:00Z",
  },
];

// Mock searchable terms with multiple definitions
export const mockSearchableTerms: SearchableTerm[] = [
  {
    id: "term_1",
    term: "serendipity",
    definitions: [
      {
        id: "def_1_1",
        definition:
          "the occurrence and development of events by chance in a happy or beneficial way",
        partOfSpeech: "noun",
        example:
          "A fortunate stroke of serendipity brought the two old friends together.",
      },
      {
        id: "def_1_2",
        definition:
          "the faculty or phenomenon of finding valuable or agreeable things not sought for",
        partOfSpeech: "noun",
        example: "The discovery was pure serendipity.",
      },
    ],
    isGenerating: false,
    generatedAt: "2024-08-30T10:00:00Z",
  },
  {
    id: "term_2",
    term: "ephemeral",
    definitions: [
      {
        id: "def_2_1",
        definition: "lasting for a very short time",
        partOfSpeech: "adjective",
        example: "The beauty of cherry blossoms is ephemeral.",
      },
      {
        id: "def_2_2",
        definition: "lasting for a markedly brief time",
        partOfSpeech: "adjective",
        example: "Fashion trends are often ephemeral.",
      },
    ],
    isGenerating: false,
    generatedAt: "2024-08-30T09:30:00Z",
  },
  {
    id: "term_3",
    term: "ubiquitous",
    definitions: [
      {
        id: "def_3_1",
        definition: "present, appearing, or found everywhere",
        partOfSpeech: "adjective",
        example: "Smartphones have become ubiquitous in modern society.",
      },
      {
        id: "def_3_2",
        definition: "existing or being everywhere at the same time",
        partOfSpeech: "adjective",
        example:
          "The ubiquitous nature of social media affects all aspects of life.",
      },
    ],
    isGenerating: false,
    generatedAt: "2024-08-30T09:00:00Z",
  },
  {
    id: "term_4",
    term: "perspicacious",
    definitions: [
      {
        id: "def_4_1",
        definition: "having a ready insight into and understanding of things",
        partOfSpeech: "adjective",
        example: "She was perspicacious enough to see through his lies.",
      },
    ],
    isGenerating: false,
    generatedAt: "2024-08-30T08:30:00Z",
  },
];
