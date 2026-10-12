import type { Meta, StoryObj } from '@storybook/react';
import { Button } from './button';

const meta = {
  title: 'UI Primitives/Button',
  component: Button,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['default', 'red', 'blue', 'yellow', 'outline', 'secondary', 'ghost', 'destructive', 'link'],
    },
    size: {
      control: 'select',
      options: ['default', 'xs', 'sm', 'lg', 'icon', 'icon-xs', 'icon-sm', 'icon-lg'],
    },
    disabled: {
      control: 'boolean',
    },
  },
} satisfies Meta<typeof Button>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    children: 'Default Button',
    variant: 'default',
  },
};

export const PrimaryRed: Story = {
  args: {
    children: 'Action Red Button',
    variant: 'red',
  },
};

export const PrimaryBlue: Story = {
  args: {
    children: 'Art Blue Button',
    variant: 'blue',
  },
};

export const PrimaryYellow: Story = {
  args: {
    children: 'Art Yellow Button',
    variant: 'yellow',
  },
};

export const Outline: Story = {
  args: {
    children: 'Outline Button',
    variant: 'outline',
  },
};

export const Secondary: Story = {
  args: {
    children: 'Secondary Button',
    variant: 'secondary',
  },
};

export const Ghost: Story = {
  args: {
    children: 'Ghost Button',
    variant: 'ghost',
  },
};

export const Destructive: Story = {
  args: {
    children: 'Destructive Button',
    variant: 'destructive',
  },
};

export const AllVariants: Story = {
  render: () => (
    <div className="flex flex-wrap gap-3 items-center">
      <Button variant="default">Default</Button>
      <Button variant="red">Red</Button>
      <Button variant="blue">Blue</Button>
      <Button variant="yellow">Yellow</Button>
      <Button variant="outline">Outline</Button>
      <Button variant="secondary">Secondary</Button>
      <Button variant="ghost">Ghost</Button>
      <Button variant="destructive">Destructive</Button>
      <Button variant="link">Link</Button>
    </div>
  ),
};

export const AllSizes: Story = {
  render: () => (
    <div className="flex flex-wrap gap-3 items-center">
      <Button size="xs">Extra Small (xs)</Button>
      <Button size="sm">Small (sm)</Button>
      <Button size="default">Default</Button>
      <Button size="lg">Large (lg)</Button>
    </div>
  ),
};
