import type { AccountProfile, LearningSettings } from '@/lib/api/account'

export function isTimezoneValid(timezone: string): boolean {
  if (!timezone || typeof timezone !== 'string') return false
  try {
    new Intl.DateTimeFormat('en', { timeZone: timezone })
    return true
  } catch {
    return false
  }
}

export function hasCompatibleQuestionTypeAndFormat(
  learning: Pick<LearningSettings, 'question_types' | 'formats'>,
  options: Pick<AccountProfile['learning_options'], 'pairs' | 'advanced_grading'>,
): boolean {
  if (!learning.question_types.length || !learning.formats.length) return false
  const allowedFormats = options.advanced_grading ? learning.formats : ['single_choice']
  return learning.question_types.some(type =>
    allowedFormats.some(format =>
      options.pairs.some(pair => pair.question_type === type && pair.format === format),
    ),
  )
}

export type LearningSettingsDraft = {
  timezone: string
  learning: LearningSettings
}

export function validateLearningSettings(
  draft: LearningSettingsDraft,
  options: AccountProfile['learning_options'],
): boolean {
  if (!isTimezoneValid(draft.timezone)) return false

  const { learning } = draft
  if (!learning || !options) return false

  if (!hasCompatibleQuestionTypeAndFormat(learning, options)) return false

  const { limits } = options
  if (!limits) return false

  if (
    learning.questions_per_sense < limits.min_questions_per_sense ||
    learning.questions_per_sense > limits.max_questions_per_sense
  ) {
    return false
  }

  if (learning.max_sense_count < 1 || learning.max_sense_count > 20) {
    return false
  }

  if (learning.questions_per_sense * learning.max_sense_count > limits.max_questions_per_prepare) {
    return false
  }

  return true
}
