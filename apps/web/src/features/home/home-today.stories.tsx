import type { Meta, StoryObj } from '@storybook/react';
import { HomeToday } from './home-today.client';
import type { StudySummary } from '@/lib/api/study';
import type { HomeResource } from '@/features/home/use-home.client';

const mockReadySummary: HomeResource<StudySummary> = {
  status: 'ready',
  data: {
    node_id: 'personal_root',
    as_of: '2026-10-10T12:00:00Z',
    total: 218,
    studied: 158,
    due: 42,
    new: 18,
    not_due: 158,
    last_studied_at: '2026-10-09T18:00:00Z',
    reachable_decks: 4,
  },
  error: null,
  retry: () => {},
};

const meta = {
  title: 'Home/TodayOverview',
  component: HomeToday,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  args: {
    summary: mockReadySummary,
    today: '2026-10-10',
  },
} satisfies Meta<typeof HomeToday>;

export default meta;
type Story = StoryObj<typeof meta>;

export const ActiveReviewsDue: Story = {
  args: {
    summary: mockReadySummary,
    today: '2026-10-10',
  },
};

export const OnlyNewWordsAvailable: Story = {
  args: {
    summary: {
      status: 'ready',
      data: {
        node_id: 'personal_root',
        as_of: '2026-10-10T12:00:00Z',
        total: 50,
        studied: 15,
        due: 0,
        new: 35,
        not_due: 15,
        last_studied_at: '2026-10-08T18:00:00Z',
        reachable_decks: 2,
      },
      error: null,
      retry: () => {},
    },
    today: '2026-10-10',
  },
};

export const AllCaughtUp: Story = {
  args: {
    summary: {
      status: 'ready',
      data: {
        node_id: 'personal_root',
        as_of: '2026-10-10T12:00:00Z',
        total: 100,
        studied: 100,
        due: 0,
        new: 0,
        not_due: 100,
        last_studied_at: '2026-10-10T09:00:00Z',
        reachable_decks: 2,
      },
      error: null,
      retry: () => {},
    },
    today: '2026-10-10',
  },
};

export const EmptyLibraryNewUser: Story = {
  args: {
    summary: {
      status: 'ready',
      data: {
        node_id: 'personal_root',
        as_of: '2026-10-10T12:00:00Z',
        total: 0,
        studied: 0,
        due: 0,
        new: 0,
        not_due: 0,
        last_studied_at: null,
        reachable_decks: 0,
      },
      error: null,
      retry: () => {},
    },
    today: '2026-10-10',
  },
};

export const LoadingState: Story = {
  args: {
    summary: {
      status: 'loading',
      data: null,
      error: null,
      retry: () => {},
    },
    today: '2026-10-10',
  },
};

export const NetworkErrorState: Story = {
  args: {
    summary: {
      status: 'error',
      data: null,
      error: new Error('Failed to synchronize daily queue. Gateway timed out.'),
      retry: () => {},
    },
    today: '2026-10-10',
  },
};
