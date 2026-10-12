import type { Meta, StoryObj } from '@storybook/react';
import { LibraryFolder } from './library-folder';

const meta = {
  title: 'Library/FolderNavigator',
  component: LibraryFolder,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  args: {
    nodeId: 'preview-personal',
    name: 'Personal Root',
    space: 'PERSONAL',
    canCreate: true,
  },
} satisfies Meta<typeof LibraryFolder>;

export default meta;
type Story = StoryObj<typeof meta>;

export const PersonalWorkspaceFolder: Story = {
  args: {
    nodeId: 'preview-personal',
    name: 'Personal Workspace',
    space: 'PERSONAL',
    canCreate: true,
  },
};

export const MeetingsFolder: Story = {
  args: {
    nodeId: 'meetings',
    name: 'Meetings & Discussions',
    space: 'PERSONAL',
    canCreate: true,
  },
};

export const PublishedPublicFolder: Story = {
  args: {
    nodeId: 'preview-published',
    name: 'Public Decks',
    space: 'PUBLISHED',
    canCreate: false,
  },
};
