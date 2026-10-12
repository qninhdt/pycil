import type { Meta, StoryObj } from '@storybook/react';
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from './dialog';
import { Button } from './button';
import { Input } from './input';
import { Label } from './label';

const meta = {
  title: 'UI Primitives/Dialog',
  component: Dialog,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof Dialog>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="red">Create Deck</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>New Vocabulary Deck</DialogTitle>
          <DialogDescription>
            Group words by theme, topic, or examination requirements.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="deck-name">Deck Name</Label>
            <Input id="deck-name" placeholder="e.g. Cambridge Academic Lexicon" />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="deck-desc">Description (Optional)</Label>
            <Input id="deck-desc" placeholder="Vocabulary for IELTS Academic Section 3" />
          </div>
        </div>
        <DialogFooter className="gap-2 sm:gap-0">
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button variant="default">Save Deck</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  ),
};
