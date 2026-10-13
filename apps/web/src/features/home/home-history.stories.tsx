import type { Meta, StoryObj } from '@storybook/react';
import { HomeStreak, HomeActivity } from './home-history.client';
import type { StudyActivity, ActivityDay } from '@/lib/api/study';
import type { HomeResource } from '@/features/home/use-home.client';
import { shiftDay } from '@/features/home/calendar';

const today = '2026-10-10';

const generateDays = (count: number): ActivityDay[] => {
  return Array.from({ length: count }, (_, i) => {
    const day = shiftDay(today, i - count + 1);
    // Simulate varied intensity
    const isStudyDay = (i % 7 !== 0) && (i % 5 !== 0);
    return {
      day,
      applied_events: isStudyDay ? (i % 3) * 5 + 2 : 0,
      practice_events: isStudyDay ? (i % 4) * 8 + 4 : 0,
    };
  });
};

const mockActivity: HomeResource<StudyActivity> = {
  status: 'ready',
  data: {
    as_of: '2026-10-10T12:00:00Z',
    timezone: 'Asia/Ho_Chi_Minh',
    start_date: shiftDay(today, -34),
    end_date: today,
    days: generateDays(35),
    current_streak: 12,
    longest_streak: 28,
    applied_events: 120,
    practice_events: 340,
  },
  error: null,
  retry: () => {},
};

const meta = {
  title: 'Home/ActivityAndStreak',
  component: HomeStreak,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  args: {
    activity: mockActivity,
    today,
  },
} satisfies Meta<typeof HomeStreak>;

export default meta;
type Story = StoryObj<typeof meta>;

export const StudyStreakTile: Story = {
  args: {
    activity: mockActivity,
    today,
  },
  render: (args) => (
    <div className="w-[380px] p-6 border border-border rounded-lg bg-card">
      <HomeStreak {...args} />
    </div>
  ),
};

export const MonthlyHeatmapActivity: Story = {
  render: () => (
    <div className="w-[600px] max-w-full p-6 border border-border rounded-lg bg-card">
      <HomeActivity activity={mockActivity} today={today} />
    </div>
  ),
};

export const FullDashboardWidget: Story = {
  render: () => (
    <div className="grid grid-cols-1 md:grid-cols-[340px_1fr] gap-6 max-w-5xl border border-border p-6 rounded-lg bg-card">
      <div className="border-r border-border pr-6 max-md:border-r-0 max-md:border-b max-md:pb-6">
        <HomeStreak activity={mockActivity} today={today} />
      </div>
      <div>
        <HomeActivity activity={mockActivity} today={today} />
      </div>
    </div>
  ),
};
