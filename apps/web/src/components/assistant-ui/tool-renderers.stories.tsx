import type { Meta, StoryObj } from '@storybook/react';
import { CustomToolResult } from './tool-renderers';

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
          kind: 'WORD',
          word_id: 1,
          lemma: 'lucid',
          entry_type: 'WORD',
          match_kind: 'EXACT',
          matched_queries: ['lucid'],
          senses: [{ sense_id: 1, word_id: 1, lemma: 'lucid', definition: 'clear and easy to understand', pos: 'ADJECTIVE' }],
          matched_surface: 'lucid',
        },
        {
          kind: 'REFERENCE',
          reference_id: 'ref-1',
          display: 'lucidity',
          entry_type: 'WORD',
          match_kind: 'PREFIX',
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
    args: { name: 'GRE Vocabulary 2026', type: 'DECK' },
    result: { node_id: '01900000-0000-7000-8000-000000000003', name: 'GRE Vocabulary 2026', type: 'DECK', summary: { total: 0 } },
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
