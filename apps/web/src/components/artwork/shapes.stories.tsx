import type { Meta, StoryObj } from '@storybook/react';
import { Shape, shapeNames, displayName, type ShapeName } from '@/components/artwork/artwork';

const meta = {
  title: 'Foundation/Shapes',
  component: Shape,
  parameters: {
    layout: 'padded',
  },
  argTypes: {
    name: {
      control: 'select',
      options: shapeNames,
    },
    tone: {
      control: 'radio',
      options: ['color', 'mono'],
    },
  },
} satisfies Meta<typeof Shape>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    name: 'circle',
    tone: 'color',
  },
  render: (args) => (
    <div className="flex flex-col items-center justify-center gap-3 p-6 border border-border rounded-lg bg-card max-w-[180px] text-center">
      <div className="size-16 flex items-center justify-center">
        <Shape name={args.name} tone={args.tone || 'color'} className="size-14" />
      </div>
      <span className="text-xs font-semibold capitalize">{displayName(args.name)}</span>
    </div>
  ),
};

export const AllShapes: Story = {
  render: (args) => (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Geometric Vocabulary</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Atomic Bauhaus primitives: circle, square, triangle, arc, ring, axis.
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-6">
        {shapeNames.map((name: ShapeName) => (
          <div
            key={name}
            className="border border-border rounded-lg p-4 bg-card flex flex-col items-center justify-center gap-3 text-center"
          >
            <div className="size-16 flex items-center justify-center">
              <Shape name={name} tone={args.tone || 'color'} className="size-14" />
            </div>
            <span className="text-xs font-semibold">{displayName(name)}</span>
          </div>
        ))}
      </div>
    </div>
  ),
  args: {
    tone: 'color',
    name: 'circle',
  },
};
