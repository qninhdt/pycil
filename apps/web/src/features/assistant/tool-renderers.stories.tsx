import type { Meta, StoryObj } from '@storybook/react';
import { CustomToolResult } from './tool-renderers.client';

const meta = {
  title: 'Assistant AI/ToolRenderers',
  component: CustomToolResult,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof CustomToolResult>;

export default meta;
type Story = StoryObj<typeof meta>;

export const DictionarySearchComplete: Story = {
  args: {
    toolName: 'search_words',
    args: { queries: ['lucid'], limit: 3 },
    result: {
      items: [
        {
          kind: 'word',
          word_id: 1,
          lemma: 'lucid',
          entry_type: 'word',
          match_kind: 'exact',
          matched_queries: ['lucid'],
          senses: [{ sense_id: 1, word_id: 1, lemma: 'lucid', definition: 'clear and easy to understand', pos: 'adjective' }],
          matched_surface: 'lucid',
        },
        {
          kind: 'reference',
          reference_id: 'ref-1',
          display: 'lucidity',
          entry_type: 'word',
          match_kind: 'prefix',
          matched_queries: ['lucid'],
          matched_surface: 'lucidity',
        },
      ],
    },
    status: { type: 'complete' },
    isError: false,
  },
  render: (args) => (
    <div className="w-[450px]">
      <CustomToolResult {...args} />
    </div>
  ),
};

export const ToolRunningState: Story = {
  args: {
    toolName: 'search_words',
    args: { queries: ['ephemeral'] },
    result: null,
    status: { type: 'running' },
    isError: false,
  },
  render: (args) => (
    <div className="w-[450px]">
      <CustomToolResult {...args} />
    </div>
  ),
};

export const NodeCreationSuccess: Story = {
  args: {
    toolName: 'create_node',
    args: { name: 'GRE Vocabulary 2026', type: 'deck' },
    result: { node_id: '01900000-0000-7000-8000-000000000003', name: 'GRE Vocabulary 2026', type: 'deck', summary: { total: 0 } },
    status: { type: 'complete' },
    isError: false,
  },
  render: (args) => (
    <div className="w-[450px]">
      <CustomToolResult {...args} />
    </div>
  ),
};

export const ToolErrorState: Story = {
  args: {
    toolName: 'search_words',
    args: { queries: ['timeout_error'] },
    result: 'Network connection timed out after 10000ms',
    status: { type: 'complete' },
    isError: true,
  },
  render: (args) => (
    <div className="w-[450px]">
      <CustomToolResult {...args} />
    </div>
  ),
};
