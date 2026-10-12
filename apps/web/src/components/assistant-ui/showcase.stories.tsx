import type { Meta, StoryObj } from '@storybook/react';
import { AssistantShowcase } from './showcase';

const meta = {
  title: 'Assistant AI/ChatThread',
  component: AssistantShowcase,
  parameters: {
    layout: 'fullscreen',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof AssistantShowcase>;

export default meta;
type Story = StoryObj<typeof meta>;

export const InteractiveChatWorkspace: Story = {
  render: () => (
    <div className="min-h-screen w-full bg-background p-4 md:p-8 flex flex-col items-center">
      <AssistantShowcase />
    </div>
  ),
};
