import type { Meta, StoryObj } from '@storybook/react';
import React, { useState } from 'react';
import {
  Icon,
  iconNames,
  compactIconNames,
  learningIconNames,
  displayName,
  type IconName,
  type CompactIconName,
  type LearningIconName,
} from '@/components/artwork/artwork';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const meta = {
  title: 'Foundation/Icons',
  parameters: {
    layout: 'padded',
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

function IconGalleryComponent() {
  const [search, setSearch] = useState('');
  const [tone, setTone] = useState<'color' | 'mono'>('color');

  const filterFn = (name: string) =>
    name.toLowerCase().includes(search.toLowerCase().trim());

  const filteredIdentity = iconNames.filter(filterFn);
  const filteredControls = compactIconNames.filter(filterFn);
  const filteredLearning = learningIconNames.filter(filterFn);

  return (
    <div className="space-y-8 max-w-6xl">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Icon Language</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Geometric icon system shared across controls, navigation, and learning modules.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Input
            placeholder="Search icons..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-48 sm:w-64"
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => setTone((prev) => (prev === 'color' ? 'mono' : 'color'))}
          >
            {tone === 'color' ? 'Switch to Mono' : 'Switch to Color'}
          </Button>
        </div>
      </div>

      {/* Identity & Content Icons */}
      <section className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h3 className="text-lg font-bold">Identity & Content Icons</h3>
          <span className="text-xs text-muted-foreground">{filteredIdentity.length} icons</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">
          {filteredIdentity.map((name: IconName) => (
            <div
              key={name}
              className="border border-border rounded-md p-3 bg-card flex flex-col items-center justify-center gap-2 hover:border-art-blue transition-colors text-center"
            >
              <div className="size-12 flex items-center justify-center">
                <Icon name={name} tone={tone} className="size-8" />
              </div>
              <span className="text-[11px] font-medium leading-tight line-clamp-1">
                {displayName(name)}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Control Icons */}
      <section className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h3 className="text-lg font-bold">Controls & System Icons</h3>
          <span className="text-xs text-muted-foreground">{filteredControls.length} icons</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">
          {filteredControls.map((name: CompactIconName) => (
            <div
              key={name}
              className="border border-border rounded-md p-3 bg-card flex flex-col items-center justify-center gap-2 hover:border-art-blue transition-colors text-center"
            >
              <div className="size-10 flex items-center justify-center">
                <Icon name={name} variant="control" tone={tone} className="size-5" />
              </div>
              <span className="text-[11px] font-medium leading-tight line-clamp-1">
                {displayName(name)}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Learning Icons */}
      <section className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h3 className="text-lg font-bold">Learning & Quiz Icons</h3>
          <span className="text-xs text-muted-foreground">{filteredLearning.length} icons</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">
          {filteredLearning.map((name: LearningIconName) => (
            <div
              key={name}
              className="border border-border rounded-md p-3 bg-card flex flex-col items-center justify-center gap-2 hover:border-art-blue transition-colors text-center"
            >
              <div className="size-12 flex items-center justify-center">
                <Icon name={name} variant="learning" tone={tone} className="size-8" />
              </div>
              <span className="text-[11px] font-medium leading-tight line-clamp-1">
                {displayName(name)}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

export const IconGallery: Story = {
  render: () => <IconGalleryComponent />,
};
