import type { Meta, StoryObj } from '@storybook/react';
import React, { useState } from 'react';
import { Flashcard, type FlashcardProps } from './flashcard.client';

const sampleContent = {
  lemma: 'lucid',
  pos: 'adjective',
  definition: 'Clearly expressed and easy to understand, or able to think clearly.',
  pronunciation: '/ˈluː.sɪd/',
  cefr_level: 'c1',
  examples: [
    { text: 'She gave a clear and [lucid] explanation of the whole complex affair.' },
    { text: 'The patient has become more [lucid] this morning.' },
  ],
};

const meta = {
  title: 'Learning/Flashcard',
  component: Flashcard,
  parameters: {
    layout: 'centered',
  },
  tags: ['autodocs'],
  args: {
    cardId: 'card-101',
    ordinal: 1,
    content: sampleContent,
    revealed: false,
    onRevealedChange: () => {},
  },
} satisfies Meta<typeof Flashcard>;

export default meta;
type Story = StoryObj<typeof meta>;

function InteractiveFlashcardWrapper(props: Partial<FlashcardProps>) {
  const [revealed, setRevealed] = useState(props.revealed ?? false);

  return (
    <div className="w-[500px] max-w-full">
      <Flashcard
        cardId="card-101"
        ordinal={1}
        content={sampleContent}
        revealed={revealed}
        onRevealedChange={setRevealed}
        {...props}
      />
    </div>
  );
}

export const FrontCard: Story = {
  render: () => <InteractiveFlashcardWrapper revealed={false} />,
};

export const RevealedBackCard: Story = {
  render: () => <InteractiveFlashcardWrapper revealed={true} />,
};

export const LongWordCard: Story = {
  render: () => (
    <div className="w-[500px] max-w-full">
      <InteractiveFlashcardWrapper
        content={{
          lemma: 'counterintuitive',
          pos: 'adjective',
          definition: 'Something that does not happen in the way you would expect it to.',
          pronunciation: '/ˌkaʊn.tər.ɪnˈtʃuː.ɪ.tɪv/',
          cefr_level: 'c2',
          examples: [
            { text: 'Steering into a skid is [counterintuitive], but it helps regain traction.' },
          ],
        }}
      />
    </div>
  ),
};
