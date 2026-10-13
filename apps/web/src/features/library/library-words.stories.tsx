import type { Meta, StoryObj } from '@storybook/react';
import { LibraryWords } from './library-words.client';
import type { StudySummary } from '@/lib/api/study';

const sampleSummary: StudySummary = {
  node_id: 'business-core',
  as_of: '2026-10-10T12:00:00Z',
  total: 24,
  studied: 18,
  due: 6,
  new: 6,
  not_due: 12,
  last_studied_at: '2026-10-09T18:00:00Z',
  reachable_decks: 1,
};

const meta = {
  title: 'Library/DeckWordList',
  component: LibraryWords,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  args: {
    nodeId: 'business-core',
    folder: false,
    editable: true,
    summary: sampleSummary,
    timezone: 'Asia/Ho_Chi_Minh',
  },
} satisfies Meta<typeof LibraryWords>;

export default meta;
type Story = StoryObj<typeof meta>;

export const DeckWithWords: Story = {
  args: {
    nodeId: 'business-core',
    folder: false,
    editable: true,
    summary: sampleSummary,
    timezone: 'Asia/Ho_Chi_Minh',
  },
};

export const ReadOnlyPublishedDeck: Story = {
  args: {
    nodeId: 'published-everyday',
    folder: false,
    editable: false,
    summary: {
      ...sampleSummary,
      node_id: 'published-everyday',
      total: 12,
      studied: 12,
      due: 0,
      new: 0,
      not_due: 12,
    },
    timezone: 'Asia/Ho_Chi_Minh',
  },
};

export const EmptyDeck: Story = {
  args: {
    nodeId: 'empty-deck',
    folder: false,
    editable: true,
    summary: {
      ...sampleSummary,
      node_id: 'empty-deck',
      total: 0,
      studied: 0,
      due: 0,
      new: 0,
      not_due: 0,
    },
    timezone: 'Asia/Ho_Chi_Minh',
  },
};
