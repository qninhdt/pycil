import type { Meta, StoryObj } from '@storybook/react';
import { AppShellFrame as AppShell } from './app-shell-frame.client';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

const meta = {
  title: 'Application Shell/AppShell',
  component: AppShell,
  parameters: {
    layout: 'fullscreen',
  },
  tags: ['autodocs'],
  args: {
    children: null,
    skipToContentText: "Skip to content",
  },
} satisfies Meta<typeof AppShell>;

export default meta;
type Story = StoryObj<typeof meta>;

export const DefaultWorkspaceView: Story = {
  render: () => (
    <AppShell skipToContentText="Skip to content">
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight">Today</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Saturday, October 10 · 42 reviews scheduled
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Due Reviews</CardTitle>
              <CardDescription>Cards scheduled for today</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-extrabold text-action-red mb-4">42</div>
              <Button variant="red">Start Review</Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>New Vocabulary</CardTitle>
              <CardDescription>Unstudied meanings</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-extrabold text-art-yellow mb-4">18</div>
              <Button variant="yellow">Learn New</Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Study Streak</CardTitle>
              <CardDescription>Consecutive active days</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-extrabold text-foreground mb-4">12 days</div>
              <p className="text-xs text-muted-foreground">Keep it going tomorrow!</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  ),
};
