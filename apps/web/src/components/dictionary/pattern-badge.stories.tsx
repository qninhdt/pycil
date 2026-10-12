import type { Meta, StoryObj } from '@storybook/react'
import { PatternBadge, PatternList } from './pattern-badge'

const meta = {
  title: 'Dictionary/PatternBadge',
  component: PatternBadge,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  args: {
    pattern: 'hard for {sb} to {do}',
    lemma: 'hard',
  },
} satisfies Meta<typeof PatternBadge>

export default meta
type Story = StoryObj<typeof meta>

export const SinglePatternWithSlots: Story = {
  args: {
    pattern: 'hard for {sb} to {do}',
    lemma: 'hard',
  },
}

export const HardPatternGallery: StoryObj = {
  render: () => (
    <div className="flex flex-col gap-4 p-6 max-w-[600px] border border-border bg-background">
      <div className="border-b border-border pb-2">
        <h3 className="text-xl font-bold">hard <span className="text-sm font-normal text-muted-foreground">adjective</span></h3>
        <p className="text-xs text-muted-foreground mt-0.5">Grammar patterns in Bauhaus blueprint aesthetic</p>
      </div>
      <PatternList
        lemma="hard"
        patterns={[
          'hard {sth}',
          'hard to {do}',
          'hard for {sb} to {do}',
          'hard {doing}',
          'hard on {sb}',
        ]}
      />
    </div>
  ),
}

export const VariousSlots: StoryObj = {
  render: () => (
    <div className="flex flex-col gap-3 p-6 max-w-[640px] border border-border bg-background">
      <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Linguistic Syntactic Variables</h4>
      <PatternList
        lemma="adapt"
        patterns={[
          'adapt {sth}',
          'adapt {sth} for {sb}',
          'adapt {sth} to {do}',
          "trait of {one's} personality",
          'subsequent to {doing}',
          'household of {num}',
        ]}
      />
    </div>
  ),
}
