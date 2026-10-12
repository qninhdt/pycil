import type { AnswerFormat } from '../../src/lib/api'
import type { PreparedSession } from '../../src/lib/home-api'

export function preparation(count = 1, format: AnswerFormat = 'SINGLE_CHOICE', questionsPerSense = 1): PreparedSession {
  const options = [{ id: 'correct', content: 'bank' }, { id: 'wrong', content: 'shore' }]
  return {
    node_id: 'deck', selection: 'NEW', max_sense_count: count,
    actual_sense_count: count, actual_question_count: count * questionsPerSense,
    preferences: { question_types: ['DEFINITION_TO_WORD'], formats: [format], questions_per_sense: questionsPerSense, max_sense_count: count },
    bundles: Array.from({ length: count }, (_, index) => ({
      sense: { id: index + 1, word_id: index + 1, pos: 'NOUN', tier: 'COMMON', definition: { id: index + 1, content: 'a financial institution', theme_id: null }, examples: [], forms: [], patterns: [], collocations: [], relations: [], cefr_level: 'A1', register: null, ipa_uk: null, ipa_us: null },
      reason: 'NEW',
      questions: Array.from({ length: questionsPerSense }, () => ({
        question: { question_artifact_id: index + 1, sense_id: index + 1, question_type: 'DEFINITION_TO_WORD', content: 'a financial institution', correct: options[0], distractors: [options[1]], target_placement: null },
        format, level: 1, options,
      })),
    })),
  }
}
