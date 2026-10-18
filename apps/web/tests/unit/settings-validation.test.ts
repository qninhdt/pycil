import { describe, expect, test } from 'vitest'
import {
  isTimezoneValid,
  hasCompatibleQuestionTypeAndFormat,
  validateLearningSettings,
  type LearningSettingsDraft,
} from '../../src/features/account/settings-validation'
import type { AccountProfile } from '../../src/lib/api/account'

const mockLearningOptions: AccountProfile['learning_options'] = {
  pairs: [
    { question_type: 'definition_to_word', format: 'single_choice', level: 1 },
    { question_type: 'definition_to_word', format: 'single_word', level: 2 },
    { question_type: 'definition_to_word', format: 'short_answer', level: 3 },
    { question_type: 'context_to_word', format: 'single_choice', level: 1 },
    { question_type: 'sentence_rewrite', format: 'short_answer', level: 3 },
  ],
  limits: {
    min_questions_per_sense: 1,
    max_questions_per_sense: 5,
    max_questions_per_prepare: 30,
    max_answer_chars: 100,
  },
  advanced_grading: true,
}

const validDraft: LearningSettingsDraft = {
  timezone: 'Asia/Ho_Chi_Minh',
  learning: {
    question_types: ['definition_to_word'],
    formats: ['single_choice'],
    questions_per_sense: 2,
    max_sense_count: 10,
  },
}

describe('isTimezoneValid', () => {
  test('accepts valid IANA timezones', () => {
    expect(isTimezoneValid('UTC')).toBe(true)
    expect(isTimezoneValid('Asia/Ho_Chi_Minh')).toBe(true)
    expect(isTimezoneValid('America/New_York')).toBe(true)
    expect(isTimezoneValid('Europe/London')).toBe(true)
  })

  test('rejects invalid or malformed timezones', () => {
    expect(isTimezoneValid('')).toBe(false)
    expect(isTimezoneValid('Mars/Phobos')).toBe(false)
    expect(isTimezoneValid('not-a-timezone')).toBe(false)
    expect(isTimezoneValid('Invalid/Zone')).toBe(false)
    expect(isTimezoneValid(null as unknown as string)).toBe(false)
    expect(isTimezoneValid(undefined as unknown as string)).toBe(false)
  })
})

describe('hasCompatibleQuestionTypeAndFormat', () => {
  test('rejects when question types or formats are empty', () => {
    expect(
      hasCompatibleQuestionTypeAndFormat(
        { question_types: [], formats: ['single_choice'] },
        mockLearningOptions,
      ),
    ).toBe(false)

    expect(
      hasCompatibleQuestionTypeAndFormat(
        { question_types: ['definition_to_word'], formats: [] },
        mockLearningOptions,
      ),
    ).toBe(false)
  })

  test('accepts when at least one question_type and format match available pairs', () => {
    expect(
      hasCompatibleQuestionTypeAndFormat(
        { question_types: ['definition_to_word'], formats: ['single_choice'] },
        mockLearningOptions,
      ),
    ).toBe(true)

    expect(
      hasCompatibleQuestionTypeAndFormat(
        { question_types: ['context_to_word'], formats: ['short_answer', 'single_choice'] },
        mockLearningOptions,
      ),
    ).toBe(true)
  })

  test('rejects when selected types and formats do not form any available pair', () => {
    // context_to_word only has single_choice in pairs, not short_answer
    expect(
      hasCompatibleQuestionTypeAndFormat(
        { question_types: ['context_to_word'], formats: ['short_answer'] },
        mockLearningOptions,
      ),
    ).toBe(false)
  })

  test('enforces single_choice only when advanced_grading is false', () => {
    const optionsWithoutAdvanced = {
      ...mockLearningOptions,
      advanced_grading: false,
    }

    // sentence_rewrite only exists with short_answer in pairs
    // With advanced_grading = false, it must match single_choice, which does not exist
    expect(
      hasCompatibleQuestionTypeAndFormat(
        { question_types: ['sentence_rewrite'], formats: ['short_answer'] },
        optionsWithoutAdvanced,
      ),
    ).toBe(false)

    // definition_to_word has single_choice in pairs
    expect(
      hasCompatibleQuestionTypeAndFormat(
        { question_types: ['definition_to_word'], formats: ['short_answer', 'single_word'] },
        optionsWithoutAdvanced,
      ),
    ).toBe(true)
  })
})

describe('validateLearningSettings', () => {
  test('validates a complete valid draft', () => {
    expect(validateLearningSettings(validDraft, mockLearningOptions)).toBe(true)
  })

  test('rejects drafts with invalid timezones', () => {
    expect(
      validateLearningSettings(
        { ...validDraft, timezone: 'Moon/Base' },
        mockLearningOptions,
      ),
    ).toBe(false)

    expect(
      validateLearningSettings(
        { ...validDraft, timezone: '' },
        mockLearningOptions,
      ),
    ).toBe(false)
  })

  test('rejects drafts with incompatible question types/formats', () => {
    expect(
      validateLearningSettings(
        {
          ...validDraft,
          learning: {
            ...validDraft.learning,
            question_types: [],
          },
        },
        mockLearningOptions,
      ),
    ).toBe(false)

    expect(
      validateLearningSettings(
        {
          ...validDraft,
          learning: {
            ...validDraft.learning,
            formats: [],
          },
        },
        mockLearningOptions,
      ),
    ).toBe(false)

    expect(
      validateLearningSettings(
        {
          ...validDraft,
          learning: {
            ...validDraft.learning,
            question_types: ['context_to_word'],
            formats: ['short_answer'],
          },
        },
        mockLearningOptions,
      ),
    ).toBe(false)
  })

  test('enforces bounds on questions_per_sense', () => {
    // Exactly at min bound
    expect(
      validateLearningSettings(
        { ...validDraft, learning: { ...validDraft.learning, questions_per_sense: 1 } },
        mockLearningOptions,
      ),
    ).toBe(true)

    // Below min bound
    expect(
      validateLearningSettings(
        { ...validDraft, learning: { ...validDraft.learning, questions_per_sense: 0 } },
        mockLearningOptions,
      ),
    ).toBe(false)

    // Exactly at max bound (with sense count adjusted to stay within total prepare limit)
    expect(
      validateLearningSettings(
        {
          ...validDraft,
          learning: { ...validDraft.learning, questions_per_sense: 5, max_sense_count: 6 },
        },
        mockLearningOptions,
      ),
    ).toBe(true)

    // Above max bound
    expect(
      validateLearningSettings(
        {
          ...validDraft,
          learning: { ...validDraft.learning, questions_per_sense: 6, max_sense_count: 5 },
        },
        mockLearningOptions,
      ),
    ).toBe(false)
  })

  test('enforces bounds on max_sense_count', () => {
    // Exactly at lower bound 1
    expect(
      validateLearningSettings(
        { ...validDraft, learning: { ...validDraft.learning, max_sense_count: 1 } },
        mockLearningOptions,
      ),
    ).toBe(true)

    // Below lower bound 1
    expect(
      validateLearningSettings(
        { ...validDraft, learning: { ...validDraft.learning, max_sense_count: 0 } },
        mockLearningOptions,
      ),
    ).toBe(false)

    expect(
      validateLearningSettings(
        { ...validDraft, learning: { ...validDraft.learning, max_sense_count: -5 } },
        mockLearningOptions,
      ),
    ).toBe(false)

    // Exactly at upper bound 20 (with questions_per_sense = 1 to stay <= 30)
    expect(
      validateLearningSettings(
        {
          ...validDraft,
          learning: { ...validDraft.learning, questions_per_sense: 1, max_sense_count: 20 },
        },
        mockLearningOptions,
      ),
    ).toBe(true)

    // Above upper bound 20
    expect(
      validateLearningSettings(
        {
          ...validDraft,
          learning: { ...validDraft.learning, questions_per_sense: 1, max_sense_count: 21 },
        },
        mockLearningOptions,
      ),
    ).toBe(false)
  })

  test('enforces total prepare questions limit (questions_per_sense * max_sense_count <= max_questions_per_prepare)', () => {
    // 2 * 15 = 30 <= 30 -> valid
    expect(
      validateLearningSettings(
        {
          ...validDraft,
          learning: { ...validDraft.learning, questions_per_sense: 2, max_sense_count: 15 },
        },
        mockLearningOptions,
      ),
    ).toBe(true)

    // 2 * 16 = 32 > 30 -> invalid
    expect(
      validateLearningSettings(
        {
          ...validDraft,
          learning: { ...validDraft.learning, questions_per_sense: 2, max_sense_count: 16 },
        },
        mockLearningOptions,
      ),
    ).toBe(false)

    // 5 * 7 = 35 > 30 -> invalid
    expect(
      validateLearningSettings(
        {
          ...validDraft,
          learning: { ...validDraft.learning, questions_per_sense: 5, max_sense_count: 7 },
        },
        mockLearningOptions,
      ),
    ).toBe(false)
  })
})
