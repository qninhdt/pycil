import type { Meta, StoryObj } from '@storybook/react';
import { Input } from './input';
import { Label } from './label';

const meta = {
  title: 'UI Primitives/Input',
  component: Input,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    type: {
      control: 'select',
      options: ['text', 'email', 'password', 'search', 'number'],
    },
    disabled: {
      control: 'boolean',
    },
    placeholder: {
      control: 'text',
    },
  },
} satisfies Meta<typeof Input>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    placeholder: 'Enter a keyword or phrase...',
    type: 'text',
    className: 'w-80',
  },
};

export const WithLabel: Story = {
  render: () => (
    <div className="grid w-80 max-w-sm items-center gap-2">
      <Label htmlFor="email-input">Email address</Label>
      <Input type="email" id="email-input" placeholder="you@pycil.ai" />
    </div>
  ),
};

export const Password: Story = {
  render: () => (
    <div className="grid w-80 max-w-sm items-center gap-2">
      <Label htmlFor="pwd-input">Password</Label>
      <Input type="password" id="pwd-input" placeholder="••••••••••••" />
    </div>
  ),
};

export const InvalidState: Story = {
  render: () => (
    <div className="grid w-80 max-w-sm items-center gap-2">
      <Label htmlFor="err-input">Username</Label>
      <Input id="err-input" defaultValue="invalid@name#" aria-invalid="true" />
      <span className="text-xs text-destructive">Usernames may only contain alphanumeric characters.</span>
    </div>
  ),
};

export const Disabled: Story = {
  args: {
    disabled: true,
    value: 'Read-only parameter',
    className: 'w-80',
  },
};
