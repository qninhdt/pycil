import type { Meta, StoryObj } from '@storybook/react';
import { WordDetail } from './dictionary-page';
import type { DictionaryWord, SenseContext } from '@/lib/dictionary-model';

const sampleWord: DictionaryWord = {
  id: 101,
  lemma: 'lucid',
  type: 'HEADWORD',
  generation_state: 'READY',
  aliases: ['lucidity', 'lucidly'],
  related: [
    { rel_type: 'SYNONYM', to_word_id: 102, to_word_lemma: 'clear' },
    { rel_type: 'ANTONYM', to_word_id: 103, to_word_lemma: 'obscure' },
  ],
  senses: [
    {
      id: 1,
      word_id: 101,
      pos: 'ADJECTIVE',
      tier: 'CORE',
      cefr_level: 'C1',
      register: 'FORMAL',
      ipa_uk: '/ˈluː.sɪd/',
      ipa_us: '/ˈluː.sɪd/',
      definition: {
        id: 1,
        content: 'Clearly expressed and easy to understand, or able to think clearly.',
        theme_id: null,
      },
      examples: [
        { id: 11, content: 'She gave a clear and [lucid|base] explanation of the whole complex affair.', theme_id: null },
        { id: 12, content: 'The patient has become much more [lucid|base] this afternoon.', theme_id: null },
      ],
      forms: [
        { surface: 'lucid', inf: 'base' },
        { surface: 'more lucid', inf: 'comparative' },
        { surface: 'most lucid', inf: 'superlative' },
      ],
      patterns: ['lucid explanation', 'lucid moment'],
      collocations: ['perfectly lucid', 'lucid intervals', 'remarkably lucid'],
      relations: [
        { rel_type: 'SYNONYM', to_word_id: 102, to_word_lemma: 'coherent', resolution_state: 'RESOLVED', to_sense_id: null },
      ],
    },
    {
      id: 2,
      word_id: 101,
      pos: 'ADJECTIVE',
      tier: 'SECONDARY',
      cefr_level: 'C2',
      register: 'SPECIALIZED',
      ipa_uk: '/ˈluː.sɪd/',
      ipa_us: '/ˈluː.sɪd/',
      definition: {
        id: 2,
        content: 'Relating to lucid dreaming, in which the dreamer is aware of dreaming.',
        theme_id: null,
      },
      examples: [
        { id: 21, content: 'He taught himself techniques for [lucid|base] dreaming to overcome nightmares.', theme_id: null },
      ],
      forms: [],
      patterns: ['lucid dream', 'lucid state'],
      collocations: ['lucid dream technique'],
      relations: [],
    },
  ],
};

const sampleContexts: SenseContext[] = [
  {
    sense_id: 1,
    learning: { state: 'DUE', due_at: '2026-10-10T08:00:00Z', last_reviewed_at: '2026-10-06T14:20:00Z' },
    decks: [{ id: 'deck_c1', name: 'Cambridge C1 Academic', owner_id: 'user_dev_01', space: 'PERSONAL' }],
    deck_count: 1,
    decks_has_more: false,
  },
  {
    sense_id: 2,
    learning: { state: 'NEW', due_at: null, last_reviewed_at: null },
    decks: [],
    deck_count: 0,
    decks_has_more: false,
  },
];

const meta = {
  title: 'Dictionary/WordDetail',
  component: WordDetail,
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
  args: {
    word: sampleWord,
    contexts: sampleContexts,
    retryContext: () => {},
    onAdd: () => {},
    onSelectWord: () => {},
  },
} satisfies Meta<typeof WordDetail>;

export default meta;
type Story = StoryObj<typeof meta>;

export const MultiSenseHeadword: Story = {
  args: {
    word: sampleWord,
    contexts: sampleContexts,
    retryContext: () => {},
    onAdd: () => {},
    onSelectWord: () => {},
  },
};

const hardWord: DictionaryWord = {
  id: 1055,
  lemma: 'hard',
  type: 'HEADWORD',
  generation_state: 'READY',
  aliases: [],
  related: [
    { rel_type: 'ANTONYM', to_word_id: 1056, to_word_lemma: 'easy' },
  ],
  senses: [
    {
      id: 201,
      word_id: 1055,
      pos: 'ADJECTIVE',
      tier: 'CORE',
      cefr_level: 'A1',
      register: null,
      ipa_uk: '/hɑːd/',
      ipa_us: '/hɑːrd/',
      definition: {
        id: 201,
        content: 'Difficult to do, understand, or deal with.',
        theme_id: null,
      },
      examples: [
        { id: 211, content: 'It is [hard|base] to know what to do for the best.', theme_id: null },
        { id: 212, content: 'She found it [hard|base] to accept the news.', theme_id: null },
      ],
      forms: [
        { surface: 'hard', inf: 'base' },
        { surface: 'harder', inf: 'comparative' },
        { surface: 'hardest', inf: 'superlative' },
      ],
      patterns: [
        'hard {sth}',
        'hard to {do}',
        'hard for {sb} to {do}',
        'hard {doing}',
        'hard on {sb}',
      ],
      collocations: ['hard work', 'hard times', 'hard choice'],
      relations: [],
    },
  ],
};

export const HardWithGrammarPatterns: Story = {
  args: {
    word: hardWord,
    contexts: [],
    retryContext: () => {},
    onAdd: () => {},
    onSelectWord: () => {},
  },
};

