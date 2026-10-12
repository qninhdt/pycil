import type { Meta, StoryObj } from '@storybook/react';
import React, { useState } from 'react';
import { WordPickerDialog } from './word-picker-dialog';
import { Button } from '@/components/ui/button';

const meta = {
  title: 'Dictionary/WordPickerDialog',
  component: WordPickerDialog,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  args: {
    open: false,
    onOpenChange: () => {},
    deckId: 'business-core',
  },
} satisfies Meta<typeof WordPickerDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

function WordPickerInteractive() {
  const [open, setOpen] = useState(false);

  return (
    <div className="p-8">
      <Button variant="red" onClick={() => setOpen(true)}>
        Open Word Picker Dialog
      </Button>
      <WordPickerDialog
        open={open}
        onOpenChange={setOpen}
        deckId="business-core"
      />
    </div>
  );
}

export const Interactive: Story = {
  render: () => <WordPickerInteractive />,
};
