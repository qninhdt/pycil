import type { Meta, StoryObj } from '@storybook/react';

const meta = {
  title: 'Foundation/Typography',
  parameters: {
    layout: 'padded',
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const TypographyScale: Story = {
  render: () => (
    <div className="space-y-8 max-w-4xl">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Typography Scale & Hierarchy</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Single geometric family: <strong>Manrope Variable</strong>. Hierarchy achieved through scale, weight, and strict proportion.
        </p>
      </div>

      <div className="divide-y divide-border border-y border-border">
        <div className="py-6 flex flex-col md:flex-row md:items-baseline justify-between gap-3">
          <span className="text-[clamp(36px,5vw,60px)] font-extrabold tracking-[-0.04em] leading-[1.05]">
            Form & function.
          </span>
          <span className="text-xs font-mono text-muted-foreground shrink-0">
            Display / Manrope 800 / clamp(36px, 5vw, 60px)
          </span>
        </div>

        <div className="py-6 flex flex-col md:flex-row md:items-baseline justify-between gap-3">
          <h1 className="text-4xl font-bold tracking-tight">
            Make room for ideas.
          </h1>
          <span className="text-xs font-mono text-muted-foreground shrink-0">
            H1 / 36px / font-bold / -0.025em
          </span>
        </div>

        <div className="py-6 flex flex-col md:flex-row md:items-baseline justify-between gap-3">
          <h2 className="text-2xl font-bold tracking-tight">
            Clear visual hierarchy.
          </h2>
          <span className="text-xs font-mono text-muted-foreground shrink-0">
            H2 / 24px / font-bold / -0.02em
          </span>
        </div>

        <div className="py-6 flex flex-col md:flex-row md:items-baseline justify-between gap-3">
          <h3 className="text-xl font-semibold tracking-tight">
            Consistent section headers.
          </h3>
          <span className="text-xs font-mono text-muted-foreground shrink-0">
            H3 / 20px / font-semibold
          </span>
        </div>

        <div className="py-6 flex flex-col md:flex-row md:items-baseline justify-between gap-3">
          <p className="text-base leading-relaxed max-w-xl">
            Useful interfaces can have a distinct point of view. Typography must be legible at speed and quiet when reading long definitions.
          </p>
          <span className="text-xs font-mono text-muted-foreground shrink-0">
            Body / 16px / leading-relaxed
          </span>
        </div>

        <div className="py-6 flex flex-col md:flex-row md:items-baseline justify-between gap-3">
          <p className="text-sm text-muted-foreground leading-normal max-w-xl">
            Secondary labels, captions, metadata, and supporting context.
          </p>
          <span className="text-xs font-mono text-muted-foreground shrink-0">
            Small / 14px / text-muted-foreground
          </span>
        </div>

        <div className="py-6 flex flex-col md:flex-row md:items-baseline justify-between gap-3">
          <code className="text-xs font-mono bg-muted px-2 py-1 rounded w-fit">
            const meaning = await dictionary.lookup('lucid')
          </code>
          <span className="text-xs font-mono text-muted-foreground shrink-0">
            Code / 12px / font-mono
          </span>
        </div>
      </div>
    </div>
  ),
};
