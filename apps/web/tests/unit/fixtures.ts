import { QueryClient } from '@tanstack/react-query'
import { waitForJob } from '../../src/lib/api/jobs'
import type { FrontendServices, PrepareInput } from '../../src/lib/api/services/contracts'
import type { AnswerFormat } from '../../src/lib/api/account'
import { parsePreparation, type PreparedSession } from '../../src/lib/api/study'

export function preparation(count = 1, format: AnswerFormat = 'single_choice', questionsPerSense = 1): PreparedSession {
  const options = [{ id: 'correct', content: 'bank' }, { id: 'wrong', content: 'shore' }]
  return {
    node_id: 'deck', selection: 'new', max_sense_count: count,
    actual_sense_count: count, actual_question_count: count * questionsPerSense,
    preferences: { question_types: ['definition_to_word'], formats: [format], questions_per_sense: questionsPerSense, max_sense_count: count },
    bundles: Array.from({ length: count }, (_, index) => ({
      sense: { id: index + 1, word_id: index + 1, pos: 'noun', tier: 'common', definition: { id: index + 1, content: 'a financial institution', theme_id: null }, examples: [], forms: [], patterns: [], collocations: [], relations: [], cefr_level: 'a1', register: null, ipa_uk: null, ipa_us: null },
      reason: 'new',
      questions: Array.from({ length: questionsPerSense }, () => ({
        question: { question_artifact_id: index + 1, sense_id: index + 1, question_type: 'definition_to_word', content: 'a financial institution', correct: options[0], distractors: [options[1]], target_placement: null },
        format, level: 1, options,
      })),
    })),
  }
}

export async function prepareSession(services: FrontendServices, input: PrepareInput, signal: AbortSignal) {
  return waitForJob(new QueryClient(), await services.learning.prepare(input, signal), services.jobs.status, parsePreparation, signal)
}
