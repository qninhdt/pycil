import type { Meta, StoryObj } from '@storybook/react';
import { LibraryHeader } from './library-header';
import type { LibraryDetails } from '@/lib/library-model';
import type { AccountProfile } from '@/lib/api';

const mockProfile: AccountProfile = {
  id: 'user_dev_01',
  display_name: 'Alex Rivera',
  handle: 'alex_r',
  bio: 'Learning cognitive science and linguistics',
  joined_at: '2026-01-15T08:00:00Z',
  plan: 'pro',
  personal_node_id: 'node_personal_root',
  published_node_id: 'node_published_root',
  library_node_id: 'node_library_root',
  learning_options: {
    pairs: [],
    limits: { min_questions_per_sense: 1, max_questions_per_sense: 4, max_questions_per_prepare: 20 },
    advanced_grading: true,
  },
  settings: {
    locale: 'en-US',
    timezone: 'Asia/Ho_Chi_Minh',
    translation_language: 'vi',
    assistant: { auto_approve: false },
    learning: {
      question_types: ['DEFINITION_TO_WORD', 'CLOZE_TO_WORD'],
      formats: ['SINGLE_CHOICE'],
      questions_per_sense: 2,
      max_sense_count: 20,
    },
  },
  effective_learning: null,
  learning_restriction: null,
};

const mockDeckDetails: LibraryDetails = {
  id: 'deck_cambridge_c1',
  name: 'Cambridge C1 Academic',
  type: 'DECK',
  description: 'Curated high-frequency vocabulary extracted from Cambridge Academic Corpus papers.',
  owner_id: 'user_dev_01',
  space: 'PERSONAL',
  role: 'NORMAL',
  created_at: '2026-02-01T10:00:00Z',
  updated_at: '2026-10-10T12:00:00Z',
  breadcrumbs: [
    { id: 'node_personal_root', name: 'Personal' },
    { id: 'folder_english', name: 'English Exams' },
    { id: 'deck_cambridge_c1', name: 'Cambridge C1 Academic' },
  ],
  summary: {
    node_id: 'deck_cambridge_c1',
    as_of: '2026-10-10T12:00:00Z',
    total: 120,
    studied: 86,
    due: 34,
    new: 15,
    not_due: 71,
    last_studied_at: '2026-10-09T18:00:00Z',
    reachable_decks: 1,
  },
  reference_available: null,
  target: null,
};

const meta = {
  title: 'Library/DeckHeader',
  component: LibraryHeader,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  args: {
    node: mockDeckDetails,
    profile: mockProfile,
    editable: true,
  },
} satisfies Meta<typeof LibraryHeader>;

export default meta;
type Story = StoryObj<typeof meta>;

export const PersonalDeckHeader: Story = {
  args: {
    node: mockDeckDetails,
    profile: mockProfile,
    editable: true,
  },
};

export const PublishedCommunityDeck: Story = {
  args: {
    node: {
      ...mockDeckDetails,
      id: 'pub_deck_01',
      name: 'IELTS Band 8.0 Vocabulary',
      description: 'Shared collection containing 240 idioms and collocations.',
      space: 'PUBLISHED',
      owner_id: 'user_tutor_vietnam',
    },
    profile: mockProfile,
    editable: false,
  },
};

export const RootFolderHeader: Story = {
  args: {
    node: {
      ...mockDeckDetails,
      id: 'node_personal_root',
      name: 'Personal',
      description: 'Your private learning space. Create decks, organize folders, and track spaced repetition.',
      breadcrumbs: [],
    },
    profile: mockProfile,
    editable: false,
  },
};
