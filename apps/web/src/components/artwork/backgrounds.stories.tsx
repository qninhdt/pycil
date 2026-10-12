import type { Meta, StoryObj } from '@storybook/react';
import React, { useState } from 'react';
import { Background, backgroundNames, displayName, type BackgroundName } from '@/components/artwork/artwork';
import { Button } from '@/components/ui/button';

const meta = {
  title: 'Foundation/Backgrounds',
  component: Background,
  parameters: {
    layout: 'padded',
  },
  args: {
    name: backgroundNames[0] || 'primary',
    tone: 'color',
  },
  argTypes: {
    name: {
      control: 'select',
      options: backgroundNames,
    },
    tone: {
      control: 'radio',
      options: ['color', 'mono'],
    },
  },
} satisfies Meta<typeof Background>;

export default meta;
type Story = StoryObj<typeof meta>;

export const SingleBackground: Story = {
  args: {
    name: backgroundNames[0] || 'primary',
    tone: 'color',
  },
  render: (args) => (
    <div className="space-y-4 max-w-2xl mx-auto">
      <div className="border border-border rounded-lg overflow-hidden bg-card h-[320px] flex items-center justify-center relative p-6">
        <Background name={args.name} tone={args.tone} className="w-full h-full" />
      </div>
      <div className="text-center">
        <h4 className="font-semibold text-sm">{displayName(args.name)}</h4>
        <p className="text-xs text-muted-foreground mt-0.5">Adaptive composition that scales to container bounds</p>
      </div>
    </div>
  ),
};

function BackgroundGalleryComponent() {
  const [tone, setTone] = useState<'color' | 'mono'>('color');

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between border-b border-border pb-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Adaptive Backgrounds</h2>
          <p className="text-sm text-muted-foreground mt-1">
            {backgroundNames.length} container-responsive geometric canvases.
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

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {backgroundNames.map((name: BackgroundName) => (
          <article
            key={name}
            className="border border-border rounded-lg overflow-hidden bg-card flex flex-col justify-between"
          >
            <div className="h-[220px] flex items-center justify-center p-4 bg-muted/10 relative overflow-hidden">
              <Background name={name} tone={tone} className="w-full h-full" />
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

export const BackgroundGallery: Story = {
  render: () => <BackgroundGalleryComponent />,
};
