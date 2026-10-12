import type { Meta, StoryObj } from '@storybook/react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from './tabs';
import { Card, CardHeader, CardTitle, CardContent } from './card';

const meta = {
  title: 'UI Primitives/Tabs',
  component: Tabs,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof Tabs>;

export default meta;
type Story = StoryObj<typeof meta>;

export const DefaultLine: Story = {
  render: () => (
    <Tabs defaultValue="overview" className="w-[450px]">
      <TabsList variant="line">
        <TabsTrigger value="overview">Overview</TabsTrigger>
        <TabsTrigger value="flashcards">Flashcards (32)</TabsTrigger>
        <TabsTrigger value="activity">Recent Activity</TabsTrigger>
      </TabsList>
      <TabsContent value="overview" className="pt-4">
        <Card>
          <CardHeader>
            <CardTitle>Deck Statistics</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Mastery level: 78%. Recommended review interval: 2 days.
            </p>
          </CardContent>
        </Card>
      </TabsContent>
      <TabsContent value="flashcards" className="pt-4">
        <div className="p-4 border border-border bg-card text-sm">
          32 cards queued for spaced repetition.
        </div>
      </TabsContent>
      <TabsContent value="activity" className="pt-4">
        <div className="p-4 border border-border bg-card text-sm">
          Last reviewed: Today at 14:20.
        </div>
      </TabsContent>
    </Tabs>
  ),
};

export const SolidPillVariant: Story = {
  render: () => (
    <Tabs defaultValue="all" className="w-[400px]">
      <TabsList variant="default">
        <TabsTrigger value="all">All Words</TabsTrigger>
        <TabsTrigger value="mastered">Mastered</TabsTrigger>
        <TabsTrigger value="learning">In Learning</TabsTrigger>
      </TabsList>
    </Tabs>
  ),
};
