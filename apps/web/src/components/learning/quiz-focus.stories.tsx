import type { Meta, StoryObj } from '@storybook/react'
import { QuizFocus } from './quiz-focus'
import type { StudySession } from '@/lib/study-session'
import type { QuestionOption, PreparedQuestion, StudyQuestion, Diagnostic, ReviewBatchResult } from '@/lib/home-api'
import type { DictionarySense } from '@/lib/dictionary-model'

const meta = {
  title: 'Learning/QuizPlayer',
  component: QuizFocus,
  parameters: {
    layout: 'fullscreen',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof QuizFocus>

export default meta
type Story = StoryObj<typeof meta>

function makeOption(id: string, content: string): QuestionOption {
  return { id, content }
}

function makeSense(id: number, wordId: number, definition: string, lemma = 'foster'): DictionarySense {
  return {
    id,
    word_id: wordId,
    definition: { id, content: definition, theme_id: null },
    examples: [{ id, content: `They [${lemma}] cooperation.`, theme_id: null }],
    pos: 'verb',
    tier: 'A2',
    forms: lemma === 'rule out'
      ? [{ surface: 'rule out', inf: 'BASE' }, { surface: 'ruled out', inf: 'PAST' }, { surface: 'ruling out', inf: 'ING' }]
      : [{ surface: lemma, inf: 'BASE' }],
    patterns: [`${lemma} something`],
    collocations: [],
    relations: [],
    cefr_level: 'B2',
    register: null,
    ipa_uk: '/ˈfɒstə(r)/',
    ipa_us: '/ˈfɑːstər/',
  }
}

function createSession({
  question,
  format = 'SINGLE_CHOICE',
  phase = 'question',
  round = 1,
  position = 0,
  outcome,
  grade,
  receipt,
  retry = [],
}: {
  question: StudyQuestion
  format?: 'SINGLE_CHOICE' | 'SINGLE_WORD' | 'SHORT_ANSWER'
  phase?: 'question' | 'feedback' | 'recap' | 'submitting' | 'complete'
  round?: number
  position?: number
  outcome?: 'clear' | 'partial' | 'miss'
  grade?: Diagnostic
  receipt?: ReviewBatchResult
  retry?: number[]
}): StudySession {
  const preparedQuestion: PreparedQuestion = {
    question,
    format,
    level: 1,
    options: [question.correct, ...question.distractors],
  }

  const sense = makeSense(
    question.sense_id,
    1,
    question.question_type === 'SENTENCE_REWRITE' ? 'exclude someone or something as a possibility' : 'encouraging or promoting development',
    question.question_type === 'SENTENCE_REWRITE' ? 'rule out' : 'foster'
  )

  return {
    version: 2,
    accountId: 'preview-alex',
    id: 'story-session-1',
    seed: 'story-seed-abc',
    prepared: {
      node_id: 'preview-library',
      selection: 'AUTO',
      max_sense_count: 10,
      actual_sense_count: 1,
      actual_question_count: 1,
      preferences: {
        question_types: [question.question_type],
        formats: [format],
        questions_per_sense: 1,
        max_sense_count: 10,
      },
      bundles: [
        {
          sense,
          reason: 'DUE',
          questions: [preparedQuestion],
        },
      ],
    },
    round,
    questions: [0],
    unseen: [],
    retry,
    position,
    draft: '',
    pendingAttempt: null,
    attempts: outcome
      ? {
          [0]: [
            {
              answer: 'user answer',
              answered_at: new Date().toISOString(),
              complete: outcome === 'clear',
              diagnostics: grade ?? (format === 'SINGLE_CHOICE' ? { correct: outcome === 'clear' } : format === 'SINGLE_WORD' ? { task_fit: outcome === 'clear', spelling_error: false, sense_id: outcome === 'clear' ? question.sense_id : null } : question.question_type === 'WORD_TO_DEFINITION' ? { sense_id: null, accuracy: null, coverage: null } : { used: false, meaning: null, form: null, construction: null, collocation: null, appropriacy: null, ...(question.question_type === 'SENTENCE_REWRITE' ? { meaning_preservation: null } : {}) }),
            },
          ],
        }
      : {},
    phase,
    submission: null,
    receipt: receipt ?? null,
  }
}

// 1. CLOZE_TO_WORD with SINGLE_WORD format
const clozeQuestion: StudyQuestion = {
  question_artifact_id: 101,
  sense_id: 1,
  question_type: 'CLOZE_TO_WORD',
  content: 'The mentor wanted to _ a welcoming environment for the entire cohort.',
  correct: makeOption('c1', 'foster'),
  distractors: [
    makeOption('d1', 'hinder'),
    makeOption('d2', 'dismiss'),
    makeOption('d3', 'stifle'),
  ],
  target_placement: null,
}

// 2. DIALOGUE_COMPLETION with SINGLE_CHOICE format (Target in Options placement)
const dialogueQuestion: StudyQuestion = {
  question_artifact_id: 102,
  sense_id: 2,
  question_type: 'DIALOGUE_COMPLETION',
  content: [
    { speaker: 'Maya', text: 'Both client leads submitted completely contradictory requirements for the Q3 release.' },
    { speaker: 'Sam', text: null },
    { speaker: 'Maya', text: 'Exactly. Resolving those tensions now prevents costly renegotiations later.' },
    { speaker: 'Sam', text: "I'll draft a unified alignment proposal and share it with both leads by 3 PM." },
  ],
  correct: makeOption('c2', 'We should [reconcile] the conflicting points before committing to the release date.'),
  distractors: [
    makeOption('d2_1', 'We should [reconcile] by ignoring both requests and shipping without review.'),
    makeOption('d2_2', 'I will [reconcile] our team budget rather than addressing their schedules.'),
    makeOption('d2_3', 'Let’s [reconcile] all future communications and cancel the project immediately.'),
  ],
  target_placement: 'OPTIONS',
}

// 2b. DIALOGUE_COMPLETION with SINGLE_CHOICE format (Target in Dialogue placement)
const dialogueInDialogueQuestion: StudyQuestion = {
  question_artifact_id: 1022,
  sense_id: 2,
  question_type: 'DIALOGUE_COMPLETION',
  content: [
    { speaker: 'Dr. Aris', text: 'The preliminary clinical trials demonstrated unusual variance in drug absorption rates.' },
    { speaker: 'Dr. Chen', text: 'Our laboratory was able to [corroborate] the initial findings with hospital pathology records.' },
    { speaker: 'Dr. Aris', text: null },
    { speaker: 'Dr. Chen', text: 'Precisely. The secondary trial verified the statistical validity within 48 hours.' },
    { speaker: 'Dr. Aris', text: 'That gives our regulatory submission solid empirical backing. Let’s finalize the report.' },
  ],
  correct: makeOption('c22', 'That was a crucial step—verifying experimental results with supporting evidence ensures rigor.'),
  distractors: [
    makeOption('d22_1', 'Why would your team contradict and disprove the trial results so prematurely?'),
    makeOption('d22_2', 'Fabricating the hospital pathology data beforehand makes the entire paper suspect.'),
    makeOption('d22_3', 'Postponing the clinical trial indefinitely until next year was the safest path.'),
  ],
  target_placement: 'DIALOGUE',
}

// 3. WORD_TO_USAGE with SHORT_ANSWER format
const usageQuestion: StudyQuestion = {
  question_artifact_id: 103,
  sense_id: 3,
  question_type: 'WORD_TO_USAGE',
  content: 'resilience — the capacity to recover quickly from difficulties; toughness',
  correct: makeOption('c3', 'The team demonstrated exceptional resilience during the system outage.'),
  distractors: [],
  target_placement: null,
}

// 4. MEANING_IN_CONTEXT with SINGLE_CHOICE format
const meaningInContextQuestion: StudyQuestion = {
  question_artifact_id: 104,
  sense_id: 4,
  question_type: 'MEANING_IN_CONTEXT',
  content: 'Her sudden [pragmatic] shift caught several conservative committee members off guard.',
  correct: makeOption('c4', 'Dealing with things sensibly and realistically based on practical considerations'),
  distractors: [
    makeOption('d4_1', 'Guided solely by rigid theoretical dogmatism'),
    makeOption('d4_2', 'Driven by uncontrollable emotional volatility'),
    makeOption('d4_3', 'Exclusively focused on aesthetic visual appeal'),
  ],
  target_placement: null,
}

// 5. WORD_TO_DEFINITION with SINGLE_CHOICE format
const wordToDefQuestion: StudyQuestion = {
  question_artifact_id: 105,
  sense_id: 5,
  question_type: 'WORD_TO_DEFINITION',
  content: 'quintessential',
  correct: makeOption('c5', 'Representing the most perfect or typical example of a quality or class'),
  distractors: [
    makeOption('d5_1', 'Relating to rapid and superficial changes in physical appearance'),
    makeOption('d5_2', 'Characterized by severe lack of precision or consistency'),
    makeOption('d5_3', 'Existing only for a very brief, fleeting moment in time'),
  ],
  target_placement: null,
}

// 6. DEFINITION_TO_WORD with SINGLE_CHOICE format
const defToWordQuestion: StudyQuestion = {
  question_artifact_id: 106,
  sense_id: 6,
  question_type: 'DEFINITION_TO_WORD',
  content: 'To make something less severe, intense, or painful; ease a burden.',
  correct: makeOption('c6', 'alleviate'),
  distractors: [
    makeOption('d6_1', 'aggravate'),
    makeOption('d6_2', 'perpetuate'),
    makeOption('d6_3', 'fabricate'),
  ],
  target_placement: null,
}

// 7. CONTEXT_TO_WORD with SINGLE_CHOICE format
const contextToWordQuestion: StudyQuestion = {
  question_artifact_id: 107,
  sense_id: 7,
  question_type: 'CONTEXT_TO_WORD',
  content: 'In this situation: After extensive negotiations over zoning laws, the council made a significant concession to local residents.',
  correct: makeOption('c7', 'concession'),
  distractors: [
    makeOption('d7_1', 'obstruction'),
    makeOption('d7_2', 'contention'),
    makeOption('d7_3', 'prohibition'),
  ],
  target_placement: null,
}

// 8. SENTENCE_REWRITE with SHORT_ANSWER format (Primary) and SINGLE_CHOICE (Secondary)
const sentenceRewriteQuestion: StudyQuestion = {
  question_artifact_id: 108,
  sense_id: 8,
  question_type: 'SENTENCE_REWRITE',
  content: 'The technician confirmed that the battery could not be causing the problem.',
  correct: makeOption('c8', 'The technician [ruled out|p] the battery as the cause of the problem.'),
  distractors: [
    makeOption('d8_1', 'The technician could not [rule out] the battery as the cause of the problem.'),
    makeOption('d8_2', 'The technician [ruled out|p] replacing the battery.'),
    makeOption('d8_3', 'The technician [ruled out|p] every cause except the battery.'),
  ],
  target_placement: null,
}

// --- Stories: 8 Question Types & Answer Formats ---

export const ClozeToWord: Story = {
  name: '1. Cloze To Word (Single Word Input)',
  render: () => <QuizFocus initialSession={createSession({ question: clozeQuestion, format: 'SINGLE_WORD' })} />,
}

export const DialogueCompletion: Story = {
  name: '2a. Dialogue Completion · Target in Options (Single Choice)',
  render: () => <QuizFocus initialSession={createSession({ question: dialogueQuestion, format: 'SINGLE_CHOICE' })} />,
}

export const DialogueCompletionInDialogue: Story = {
  name: '2b. Dialogue Completion · Target in Dialogue (Single Choice)',
  render: () => <QuizFocus initialSession={createSession({ question: dialogueInDialogueQuestion, format: 'SINGLE_CHOICE' })} />,
}

export const WordToUsage: Story = {
  name: '3. Word To Usage (Short Answer Textarea)',
  render: () => <QuizFocus initialSession={createSession({ question: usageQuestion, format: 'SHORT_ANSWER' })} />,
}

export const MeaningInContext: Story = {
  name: '4. Meaning In Context (Blockquote + Choice)',
  render: () => <QuizFocus initialSession={createSession({ question: meaningInContextQuestion, format: 'SINGLE_CHOICE' })} />,
}

export const WordToDefinition: Story = {
  name: '5. Word To Definition (Big Bauhaus Heading)',
  render: () => <QuizFocus initialSession={createSession({ question: wordToDefQuestion, format: 'SINGLE_CHOICE' })} />,
}

export const DefinitionToWord: Story = {
  name: '6. Definition To Word (Choose Lemma)',
  render: () => <QuizFocus initialSession={createSession({ question: defToWordQuestion, format: 'SINGLE_CHOICE' })} />,
}

export const ContextToWord: Story = {
  name: '7. Context To Word (Situation Paragraph)',
  render: () => <QuizFocus initialSession={createSession({ question: contextToWordQuestion, format: 'SINGLE_CHOICE' })} />,
}

export const SentenceRewriteShortAnswer: Story = {
  name: '8a. Sentence Rewrite (Short Answer Primary)',
  render: () => <QuizFocus initialSession={createSession({ question: sentenceRewriteQuestion, format: 'SHORT_ANSWER' })} />,
}

export const SentenceRewriteSingleChoice: Story = {
  name: '8b. Sentence Rewrite (Single Choice)',
  render: () => <QuizFocus initialSession={createSession({ question: sentenceRewriteQuestion, format: 'SINGLE_CHOICE' })} />,
}

export const SentenceRewriteFeedback: Story = {
  name: '8c. Sentence Rewrite (Feedback & Comparison)',
  render: () => (
    <QuizFocus
      initialSession={createSession({
        question: sentenceRewriteQuestion,
        format: 'SHORT_ANSWER',
        phase: 'feedback',
        outcome: 'clear',
      })}
    />
  ),
}

// --- Stories: Feedback Phases & Outcomes ---

export const FeedbackClear: Story = {
  name: 'Feedback: Clear (Correct Answer)',
  render: () => (
    <QuizFocus
      initialSession={createSession({
        question: defToWordQuestion,
        phase: 'feedback',
        outcome: 'clear',
      })}
    />
  ),
}

export const FeedbackPartialWithGrading: Story = {
  name: 'Feedback: Partial (AI Assessment Details)',
  render: () => (
    <QuizFocus
      initialSession={createSession({
        question: usageQuestion,
        format: 'SHORT_ANSWER',
        phase: 'feedback',
        outcome: 'partial',
        grade: {
          used: true,
          meaning: 'APPROXIMATE',
          form: 'SPELLING_ERROR',
          construction: true,
          collocation: true,
          appropriacy: true,
        },
      })}
    />
  ),
}

export const FeedbackMiss: Story = {
  name: 'Feedback: Miss (Incorrect Answer)',
  render: () => (
    <QuizFocus
      initialSession={createSession({
        question: clozeQuestion,
        format: 'SINGLE_WORD',
        phase: 'feedback',
        outcome: 'miss',
      })}
    />
  ),
}

// --- Stories: Round Recap & Session Complete ---

export const RoundRecap: Story = {
  name: 'Round Recap (Pass Summary & Retry List)',
  render: () => (
    <QuizFocus
      initialSession={createSession({
        question: defToWordQuestion,
        phase: 'recap',
        round: 1,
        retry: [0],
        outcome: 'miss',
      })}
    />
  ),
}

export const SessionComplete: Story = {
  name: 'Session Complete (Mastery Levels)',
  render: () => (
    <QuizFocus
      initialSession={createSession({
        question: defToWordQuestion,
        phase: 'complete',
        receipt: {
          accepted_at: new Date().toISOString(),
          activity_day: '2026-10-10',
          results: [1, 2, 3, 4].map((sense_id, index) => ({ sense_id, elo: 600 + index * 200, level: index + 1, stability: 1, difficulty: 5, applied: true, last_exposure_at: new Date().toISOString(), due_after: new Date(Date.now() + 86400000).toISOString() })),
          evidence: [],
        },
      })}
    />
  ),
}

export const StartScreen: Story = {
  name: 'Start Screen (Session Entry Point)',
  render: () => <QuizFocus />,
}
