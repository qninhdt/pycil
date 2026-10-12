import type { Meta, StoryObj } from '@storybook/react';
import { LibrarySummary } from './library-summary';
import type { StudySummary } from '@/lib/home-api';

const sampleSummary: StudySummary = {
  node_id: 'deck_c1',
  as_of: '2026-10-10T12:00:00Z',
  total: 142,
  studied: 104,
  due: 38,
  new: 24,
  not_due: 80,
  last_studied_at: '2026-10-09T18:00:00Z',
  reachable_decks: 3,
};

const meta = {
  title: 'Library/DeckSummary',
  component: LibrarySummary,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  args: {
    summary: sampleSummary,
  },
} satisfies Meta<typeof LibrarySummary>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ActiveDeckProgress: Story = {
  args: {
    summary: sampleSummary,
  },
};

export const HeavyDueBacklog: Story = {
  args: {
    summary: {
      node_id: 'deck_backlog',
      as_of: '2026-10-10T12:00:00Z',
      total: 350,
      studied: 330,
      due: 180,
      new: 20,
      not_due: 150,
      last_studied_at: '2026-09-20T18:00:00Z',
      reachable_decks: 1,
    },
  },
};

export const AllMasteredOrScheduled: Story = {
  args: {
    summary: {
      node_id: 'deck_scheduled',
      as_of: '2026-10-10T12:00:00Z',
      total: 85,
      studied: 85,
      due: 0,
      new: 0,
      not_due: 85,
      last_studied_at: '2026-10-10T09:00:00Z',
      reachable_decks: 1,
    },
  },
};

export const BrandNewDeck: Story = {
  args: {
    summary: {
      node_id: 'deck_brand_new',
      as_of: '2026-10-10T12:00:00Z',
      total: 50,
      studied: 0,
      due: 0,
      new: 50,
      not_due: 0,
      last_studied_at: null,
      reachable_decks: 1,
    },
  },
};
