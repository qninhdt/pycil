import type { Meta, StoryObj } from '@storybook/react';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from './card';
import { Button } from './button';
import { Badge } from './badge';

const meta = {
  title: 'UI Primitives/Card',
  component: Card,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Card className="w-[360px]">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Vocabulary Deck</CardTitle>
          <Badge variant="secondary">C1 Advanced</Badge>
        </div>
        <CardDescription>Daily Cambridge high-frequency academic words</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-muted-foreground text-sm">
          Contains 48 flashcards covering subtle nuances, word formations, and collocations.
        </p>
      </CardContent>
      <CardFooter className="flex justify-between items-center">
        <span className="text-xs text-muted-foreground">Updated today</span>
        <Button size="sm" variant="red">
          Start Practice
        </Button>
      </CardFooter>
    </Card>
  ),
};

export const SmallSize: Story = {
  render: () => (
    <Card size="sm" className="w-[300px]">
      <CardHeader>
        <CardTitle>Compact Card</CardTitle>
        <CardDescription>Small density card</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-muted-foreground">Useful in tight sidebars or grids.</p>
      </CardContent>
    </Card>
  ),
};
