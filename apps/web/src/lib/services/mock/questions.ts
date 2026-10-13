import type { MockDatabase } from '../mock'
import type { AnswerFormat, LearningSettings } from '../../api'
import type { GradeResult, PreparedQuestion, PreparedSession, QuestionOption, QuestionType, ReviewBatchResult, GradeInput, SubmittedResult, Diagnostic } from '../../home-api'
import { HomeApiError, parseGrade, parsePreparation, parseReviewBatch } from '../../home-api'
import type { DictionarySense, DictionaryWord } from '../../dictionary-model'
import type { LibraryDetails, Meaning } from '../../library-model'
import { parseMarkedText } from '../../marked-text'

const types: QuestionType[] = ['definition_to_word','context_to_word','cloze_to_word','word_to_definition','word_to_usage','dialogue_completion','meaning_in_context','sentence_rewrite']
const pairs: Record<QuestionType, AnswerFormat[]> = {
  definition_to_word: ['single_choice','single_word'], context_to_word: ['single_choice','single_word'],
  cloze_to_word: ['single_choice','single_word'], word_to_definition: ['single_choice','short_answer'],
  word_to_usage: ['single_choice','short_answer'], dialogue_completion: ['single_choice'], meaning_in_context: ['single_choice'],
  sentence_rewrite: ['short_answer','single_choice'],
}
const strip = (value: string) => parseMarkedText(value).text
const hide = (value: string) => value.replace(/\[[^\]\[|]+(?:\|[a-z0-9]+)?\]/i, '_')
const normalize = (value: string) => value.trim().toLocaleLowerCase('en').replace(/[.,!?;:]+$/g, '').replace(/\s+/g, ' ')

export function createMockQuestions(db: MockDatabase, library: {
  details: (id: string) => LibraryDetails
  meanings: (id: string, options: { state?: 'all' | 'new' | 'due' | 'not_yet_due'; limit?: number; cursor?: string }) => { senses: Meaning[]; next_cursor: string | null }
  setLearning: (senseId: number) => void
}, now: () => Date) {
  const words = db.dictionary.words as DictionaryWord[]
  const entries = words.flatMap(word => word.senses.map(sense => ({ word, sense })))
  const bySense = new Map(entries.map(entry => [entry.sense.id, entry]))
  const receipts = new Map<string, { body: string; result: ReviewBatchResult }>()
  let cursor = 0

  function option(id: string, content: string): QuestionOption { return { id, content } }
  function others(sense: DictionarySense, kind: QuestionType, count: number): { word: DictionaryWord; sense: DictionarySense }[] {
    const pool = entries.filter(item => item.sense.id !== sense.id && (kind === 'definition_to_word' || kind === 'context_to_word' || kind === 'cloze_to_word' ? item.word.id !== sense.word_id : true))
    return Array.from({ length: 3 }, (_, index) => pool[(sense.id * 7 + count * 11 + index * 13) % pool.length])
  }
  function build(word: DictionaryWord, sense: DictionarySense, kind: QuestionType, variant: number): PreparedQuestion {
    const qid = sense.id * 1000 + types.indexOf(kind) * 100 + variant + 1
    const definition = sense.definition?.content ?? `the meaning of ${word.lemma}`
    const source = sense.examples[variant % Math.max(1, sense.examples.length)]?.content ?? `They use [${word.lemma}] in this context.`
    const forms = [{ surface: word.lemma, inf: 'base' }, ...sense.forms].sort((a, b) => b.surface.length - a.surface.length)
    const form = forms.find(value => new RegExp(`\\b${value.surface.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i').test(source))
    const codes: Record<string, string> = { base: '', past: 'p', past_participle: 'pp', PRESENT_3SG: '3', ing: 'ing', plural: 'pl', comparative: 'c', superlative: 's' }
    const example = parseMarkedText(source).spans.length ? source : form ? source.replace(new RegExp(`\\b${form.surface.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i'), match => `[${match}${codes[form.inf] ? '|' + codes[form.inf] : ''}]`)
      : sense.examples.find(value => parseMarkedText(value.content).spans.length)?.content ?? `They use [${word.lemma}] in this context.`
    const distractors = others(sense, kind, variant)
    let content: string | { speaker: string; text: string | null }[] = definition
    let correctText = word.lemma
    let wrongTexts = distractors.map(entry => entry.word.lemma)
    let target_placement: 'dialogue' | 'options' | null = null
    if (kind === 'context_to_word') content = `In this situation: “${strip(hide(example)).replace('_', '…')}” — ${definition}.`
    if (kind === 'cloze_to_word') {
      content = hide(example).includes('_') ? hide(example) : `To express “${definition}”, use _.`
      correctText = parseMarkedText(example).spans[0]?.surface ?? word.lemma
    }
    if (kind === 'word_to_definition') {
      content = `[${word.lemma}]`; correctText = definition
      wrongTexts = distractors.map(entry => entry.sense.definition?.content ?? `another meaning of ${entry.word.lemma}`)
    }
    if (kind === 'word_to_usage') {
      content = `[${word.lemma}] — ${definition}`; correctText = example
      wrongTexts = distractors.map(entry => entry.sense.examples[0]?.content ?? `They discussed ${entry.word.lemma}.`)
    }
    if (kind === 'dialogue_completion') {
      target_placement = variant % 2 ? 'options' : 'dialogue'
      const partner = variant % 2 ? 'Maya' : 'Alex'
      const learner = variant % 2 ? 'Noah' : 'Sam'
      if (target_placement === 'options') {
        content = [
          { speaker: partner, text: `We need to resolve the ambiguity around “${definition}” before tomorrow's milestone.` },
          { speaker: learner, text: null },
          { speaker: partner, text: `That’s exactly right; let’s make sure the entire team adopts that wording.` },
          { speaker: learner, text: `Understood. I will publish the updated guidelines shortly.` },
        ]
        correctText = `I suggest we [${word.lemma}] because that addresses ${definition}.`
        wrongTexts = distractors.map(entry => `I suggest we [${word.lemma}] because that addresses ${entry.sense.definition?.content ?? entry.word.lemma}.`)
      } else {
        content = [
          { speaker: partner, text: `I reviewed the proposal earlier today, and they decided to ${example}.` },
          { speaker: learner, text: null },
          { speaker: partner, text: `Exactly. It kept the project on track without unnecessary friction.` },
          { speaker: learner, text: `Glad to hear that. I'll share the summary in our next sync.` },
        ]
        correctText = `That sounds very practical—it directly accounts for ${definition}.`
        wrongTexts = distractors.map(entry => `Wait, wouldn't that imply ${entry.sense.definition?.content ?? entry.word.lemma} instead?`)
      }
    }
    if (kind === 'meaning_in_context') {
      content = example; correctText = definition
      wrongTexts = distractors.map(entry => entry.sense.definition?.content ?? `another meaning of ${entry.word.lemma}`)
    }
    if (kind === 'sentence_rewrite') {
      content = `The technician confirmed that the battery could not be causing the problem.`
      correctText = `The technician [${word.lemma}|p] the battery as the cause of the problem.`
      wrongTexts = distractors.map(entry => `The technician could not [${word.lemma}] the battery.`)
    }
    const correct = option(`${qid}:c`, correctText)
    const wrong = wrongTexts.map((value, index) => option(`${qid}:${index}`, value))
    const pool = [correct, ...wrong], rotate = variant % pool.length
    const options = [...pool.slice(rotate), ...pool.slice(0, rotate)]
    return { question: { question_artifact_id: qid, sense_id: sense.id, question_type: kind, content, correct, distractors: wrong,
      target_placement }, format: 'single_choice', level: 1, options }
  }
  function prepare(input: { node_id: string; selection: 'due' | 'new' | 'auto'; max_sense_count?: number; questions_per_sense?: number }, preferences: LearningSettings): PreparedSession {
    library.details(input.node_id)
    const target = input.max_sense_count ?? preferences.max_sense_count, k = input.questions_per_sense ?? preferences.questions_per_sense
    if (!Number.isInteger(target) || target < 1 || target > 20 || !Number.isInteger(k) || k < 1 || k > 3) throw new HomeApiError(422, 'invalid_preparation')
    const all: Meaning[] = []
    let pageCursor: string | undefined
    do {
      const page = library.meanings(input.node_id, { state: 'all', limit: 100, cursor: pageCursor })
      all.push(...page.senses); pageCursor = page.next_cursor ?? undefined
    } while (pageCursor)
    const due = all.filter(item => item.learning?.state === 'due'), fresh = all.filter(item => item.learning?.state === 'new')
    const early = all.filter(item => item.learning?.state === 'not_yet_due')
    const selected = (input.selection === 'due' ? due : input.selection === 'new' ? fresh : [...due, ...fresh, ...early]).slice(0, target)
    const enabled = types.filter(kind => preferences.question_types.includes(kind) && pairs[kind].some(format => preferences.formats.includes(format)))
    if (!enabled.length) throw new HomeApiError(422, 'infeasible_learning_preferences')
    const bundles = selected.map(item => {
      const entry = bySense.get(item.sense_id)
      if (!entry) throw new HomeApiError(409, 'learning_content_changed')
      const reason = item.learning!.state
      const level = reason === 'new' ? 1 : 3
      const enabledPairs = db.account.learning_options.pairs.filter(pair => enabled.includes(pair.question_type as QuestionType) && preferences.formats.includes(pair.format as AnswerFormat))
      const normal = enabledPairs.filter(pair => pair.level <= level)
      const eligible = normal.length ? normal : enabledPairs.filter(pair => pair.level === Math.min(...enabledPairs.map(pair => pair.level)))
      const levels = [...new Set(eligible.map(pair => pair.level))]
      const totalWeight = levels.reduce((total, value) => total + 2 ** (value - level), 0)
      const questions = Array.from({ length: k }, (_, index) => {
        let draw = Math.random() * totalWeight
        const chosenLevel = levels.find(value => (draw -= 2 ** (value - level)) < 0) ?? levels.at(-1)!
        const pool = eligible.filter(pair => pair.level === chosenLevel)
        const pair = pool[Math.floor(Math.random() * pool.length)]
        return { ...build(entry.word, entry.sense, pair.question_type as QuestionType, (cursor + index) % 8), format: pair.format as AnswerFormat, level: pair.level }
      })
      return { sense: entry.sense, reason, questions }
    })
    cursor++
    return parsePreparation({ node_id: input.node_id, selection: input.selection, max_sense_count: target, actual_sense_count: bundles.length,
      actual_question_count: bundles.length * k, preferences: { ...preferences, max_sense_count: target, questions_per_sense: k }, bundles })
  }
  function grade(input: GradeInput): GradeResult {
    // shortcut: semantic grading is illustrative in the design preview; live mode uses backend grading.
    if (input.format === 'single_choice') throw new HomeApiError(422, 'invalid_grade_request')
    const senseId = Math.floor(input.question_artifact_id / 1000), entry = bySense.get(senseId)
    if (!entry) throw new HomeApiError(404, 'question_artifact_not_found')
    const kind = input.question_type, variant = input.question_artifact_id % 100 - 1
    if (!kind || variant < 0 || variant > 7 || !pairs[kind].includes(input.format)) throw new HomeApiError(422, 'unsupported_question_format')
    const answer = normalize(input.answer ?? ''), word = normalize(entry.word.lemma), definition = normalize(entry.sense.definition?.content ?? '')
    const response = (diagnostics: Diagnostic) => parseGrade({ question_artifact_id: input.question_artifact_id, question_type: kind, format: input.format, diagnostics })
    if (input.format === 'single_word') {
      const expected = normalize(build(entry.word, entry.sense, kind, variant).question.correct.content)
      const matched = entries.find(item => normalize(item.word.lemma) === answer)
      const spelling_error = answer !== expected && Math.abs(answer.length - expected.length) <= 1 && answer.slice(0, 2) === expected.slice(0, 2) && !matched
      return response({ task_fit: answer === expected || spelling_error || Boolean(matched), spelling_error,
        sense_id: spelling_error ? senseId : answer === expected ? senseId : matched?.sense.id ?? null })
    }
    if (kind === 'word_to_definition') {
      const terms = definition.split(/\W+/).filter(term => term.length > 4)
      const hits = terms.filter(term => answer.includes(term)).length
      return response({ sense_id: hits ? senseId : null, accuracy: hits >= Math.min(2, terms.length) ? 'accurate' : hits ? 'mixed' : null,
        coverage: hits >= Math.min(2, terms.length) ? 'sufficient' : hits ? 'partial' : null })
    }
    const used = answer.includes(word)
    const meaning = used && (definition.split(/\W+/).some(term => term.length > 4 && answer.includes(term)) || answer.length > word.length + 25) ? 'correct' : used ? 'approximate' : null
    return response({ used, meaning, form: used ? 'correct' : null, construction: used ? true : null, collocation: used ? true : null, appropriacy: used ? true : null,
      ...(kind === 'sentence_rewrite' ? { meaning_preservation: used ? 'preserved' as const : null } : {}) })
  }
  function review(input: { results: SubmittedResult[]; key: string }): ReviewBatchResult {
    const body = JSON.stringify(input.results), previous = receipts.get(input.key)
    if (previous) { if (previous.body !== body) throw new HomeApiError(409, 'review_batch_conflict'); return previous.result }
    if (!input.results.length || input.results.length > 60) throw new HomeApiError(422, 'invalid_review_batch')
    const accepted = now().toISOString(), date = accepted.slice(0, 10)
    // shortcut: preview receipts show fixed sample memory/mastery; only the backend updates real learning state.
    const evidence = input.results.map(item => {
      parseGrade(item)
      const senseId = Math.floor(item.question_artifact_id / 1000)
      if (!bySense.has(senseId)) throw new HomeApiError(422, 'sense_not_found')
      return { ...item, evaluated_sense_id: senseId, recall: null, performance: null, opponent_elo: 800, policy_version: 1 }
    })
    const results = [...new Set(evidence.map(item => item.evaluated_sense_id))].map(sense_id => {
      library.setLearning(sense_id)
      return { sense_id, applied: true, elo: 600, level: 1, stability: 1, difficulty: 5, last_exposure_at: accepted, due_after: new Date(now().getTime() + 86400000).toISOString() }
    })
    const result = parseReviewBatch({ accepted_at: accepted, activity_day: date, results, evidence })
    receipts.set(input.key, { body, result })
    return result
  }

  return { prepare, grade, review }
}
