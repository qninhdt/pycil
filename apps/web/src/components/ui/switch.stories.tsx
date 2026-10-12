import type { Meta, StoryObj } from '@storybook/react';
import { Switch } from './switch';
import { Label } from './label';

const meta = {
  title: 'UI Primitives/Switch',
  component: Switch,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    size: {
      control: 'radio',
      options: ['default', 'sm'],
    },
    disabled: {
      control: 'boolean',
    },
    defaultChecked: {
      control: 'boolean',
    },
  },
} satisfies Meta<typeof Switch>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <div className="flex items-center gap-3">
      <Switch id="switch-default" />
      <Label htmlFor="switch-default" className="cursor-pointer">
        Notifications
      </Label>
    </div>
  ),
};

export const Checked: Story = {
  render: () => (
    <div className="flex items-center gap-3">
      <Switch id="switch-checked" defaultChecked />
      <Label htmlFor="switch-checked" className="cursor-pointer">
        High contrast mode (Active)
      </Label>
    </div>
  ),
};

export const Small: Story = {
  render: () => (
    <div className="flex items-center gap-3">
      <Switch id="switch-small" size="sm" defaultChecked />
      <Label htmlFor="switch-small" className="cursor-pointer text-xs">
        Compact view (Small toggle)
      </Label>
    </div>
  ),
};

export const WithLabel: Story = {
  render: () => (
    <div className="flex items-center gap-3">
      <Switch id="dark-mode" defaultChecked />
      <Label htmlFor="dark-mode" className="cursor-pointer">
        Enable dark mode automatically
      </Label>
    </div>
  ),
};

export const Disabled: Story = {
  render: () => (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <Switch id="d1" disabled />
        <Label htmlFor="d1" className="text-muted-foreground">Disabled unchecked</Label>
      </div>
      <div className="flex items-center gap-3">
        <Switch id="d2" disabled defaultChecked />
        <Label htmlFor="d2" className="text-muted-foreground">Disabled checked</Label>
      </div>
    </div>
  ),
};
