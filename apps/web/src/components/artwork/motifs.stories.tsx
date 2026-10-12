import type { Meta, StoryObj } from '@storybook/react';
import React, { useState } from 'react';
import { Motif, motifNames, displayName, type MotifName } from '@/components/artwork/artwork';
import { Button } from '@/components/ui/button';

const meta = {
  title: 'Foundation/Motifs',
  component: Motif,
  parameters: {
    layout: 'padded',
  },
  args: {
    name: 'double-arch',
    tone: 'color',
  },
  argTypes: {
    name: {
      control: 'select',
      options: motifNames,
    },
    tone: {
      control: 'radio',
      options: ['color', 'mono'],
    },
  },
} satisfies Meta<typeof Motif>;

export default meta;
type Story = StoryObj<typeof meta>;

export const SingleMotif: Story = {
  args: {
    name: 'double-arch',
    tone: 'color',
  },
  render: (args) => (
    <div className="flex flex-col items-center justify-center p-8 border border-border rounded-lg bg-card max-w-md mx-auto">
      <div className="h-44 flex items-center justify-center w-full">
        <Motif name={args.name} tone={args.tone} className="max-w-[200px] h-[140px]" />
      </div>
      <span className="text-sm font-semibold mt-4">{displayName(args.name)}</span>
    </div>
  ),
};

function MotifGalleryComponent() {
  const [tone, setTone] = useState<'color' | 'mono'>('color');

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between border-b border-border pb-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Bauhaus Motifs</h2>
          <p className="text-sm text-muted-foreground mt-1">
            {motifNames.length} hand-crafted compositions: solids, outlines, counterforms, and construction axes.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setTone((prev) => (prev === 'color' ? 'mono' : 'color'))}
        >
          {tone === 'color' ? 'View Monochrome' : 'View Color'}
        </Button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {motifNames.map((name: MotifName) => (
          <article
            key={name}
            className="border border-border rounded-lg overflow-hidden bg-card flex flex-col justify-between"
          >
            <div className="h-36 flex items-center justify-center p-4 bg-muted/20">
              <Motif name={name} tone={tone} className="max-w-[180px] h-[120px]" />
            </div>
            <div className="border-t border-border p-3 flex items-center justify-between">
              <span className="text-xs font-semibold">{displayName(name)}</span>
              <code className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded font-mono">
                {name}
              </code>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

export const MotifGallery: Story = {
  render: () => <MotifGalleryComponent />,
};
