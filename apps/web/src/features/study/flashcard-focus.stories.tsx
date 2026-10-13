import type { Meta, StoryObj } from '@storybook/react';
import { FlashcardFocus } from './flashcard-focus.client';

const meta = {
  title: 'Learning/FlashcardPlayer',
  component: FlashcardFocus,
  parameters: {
    layout: 'fullscreen',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof FlashcardFocus>;

export default meta;
type Story = StoryObj<typeof meta>;

export const DefaultPlayer: Story = {
  render: () => <FlashcardFocus />,
};
