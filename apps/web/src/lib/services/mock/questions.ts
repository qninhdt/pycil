import type { MockDatabase } from '../mock'
import type { AnswerFormat, LearningSettings } from '../../api'
import type { GradeResult, PreparedBundle, PreparedQuestion, PreparedSession, QuestionOption, QuestionType, ReviewBatchResult, Rating } from '../../home-api'
import { HomeApiError, parseGrade, parsePreparation, parseReviewBatch } from '../../home-api'
import type { DictionarySense, DictionaryWord } from '../../dictionary-model'
import type { LibraryDetails, Meaning } from '../../library-model'

const types: QuestionType[] = ['DEFINITION_TO_WORD','CONTEXT_TO_WORD','CLOZE_TO_WORD','WORD_TO_DEFINITION','WORD_TO_USAGE','DIALOGUE_COMPLETION','MEANING_IN_CONTEXT']
const pairs: Record<QuestionType, AnswerFormat[]> = {
  DEFINITION_TO_WORD: ['SINGLE_CHOICE','SINGLE_WORD'], CONTEXT_TO_WORD: ['SINGLE_CHOICE','SINGLE_WORD'],
  CLOZE_TO_WORD: ['SINGLE_CHOICE','SINGLE_WORD'], WORD_TO_DEFINITION: ['SINGLE_CHOICE','SHORT_ANSWER'],
  WORD_TO_USAGE: ['SINGLE_CHOICE','SHORT_ANSWER'], DIALOGUE_COMPLETION: ['SINGLE_CHOICE'], MEANING_IN_CONTEXT: ['SINGLE_CHOICE'],
}
const strip = (value: string) => value.replace(/<t\b[^>]*>(.*?)<\/t>/gi, '$1')
const hide = (value: string) => value.replace(/<t\b[^>]*>.*?<\/t>/i, '_')
const normalize = (value: string) => value.trim().toLocaleLowerCase('en').replace(/[.,!?;:]+$/g, '').replace(/\s+/g, ' ')

export function createMockQuestions(db: MockDatabase, library: {
  details: (id: string) => LibraryDetails
  meanings: (id: string, options: { state?: 'ALL' | 'NEW' | 'DUE' | 'NOT_YET_DUE'; limit?: number; cursor?: string }) => { senses: Meaning[]; next_cursor: string | null }
  setLearning: (senseId: number, rating: Rating) => void
}, now: () => Date) {
  const words = db.dictionary.words as DictionaryWord[]
  const entries = words.flatMap(word => word.senses.map(sense => ({ word, sense })))
  const bySense = new Map(entries.map(entry => [entry.sense.id, entry]))
  const receipts = new Map<string, { body: string; result: ReviewBatchResult }>()
  let cursor = 0

  function option(id: string, content: string, explanation: string): QuestionOption { return { id, content, explanation } }
  function others(sense: DictionarySense, kind: QuestionType, count: number): { word: DictionaryWord; sense: DictionarySense }[] {
    const pool = entries.filter(item => item.sense.id !== sense.id && (kind === 'DEFINITION_TO_WORD' || kind === 'CONTEXT_TO_WORD' || kind === 'CLOZE_TO_WORD' ? item.word.id !== sense.word_id : true))
    return Array.from({ length: 3 }, (_, index) => pool[(sense.id * 7 + count * 11 + index * 13) % pool.length])
  }
  function build(word: DictionaryWord, sense: DictionarySense, kind: QuestionType, variant: number): PreparedQuestion {
    const qid = sense.id * 1000 + types.indexOf(kind) * 100 + variant + 1
    const definition = sense.definition?.content ?? `the meaning of ${word.lemma}`
    const source = sense.examples[variant % Math.max(1, sense.examples.length)]?.content ?? `They use <t inf="base">${word.lemma}</t> in this context.`
    const forms = [{ surface: word.lemma, inf: 'BASE' }, ...sense.forms].sort((a, b) => b.surface.length - a.surface.length)
    const form = forms.find(value => new RegExp(`\\b${value.surface.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i').test(source))
    const example = source.includes('<t ') ? source : form ? source.replace(new RegExp(`\\b${form.surface.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i'), match => `<t inf="${form.inf.toLowerCase()}">${match}</t>`)
      : sense.examples.find(value => value.content.includes('<t '))?.content ?? `They use <t inf="base">${word.lemma}</t> in this context.`
    const distractors = others(sense, kind, variant)
    let content: string | { speaker: string; text: string | null }[] = definition
    let correctText = word.lemma
    let wrongTexts = distractors.map(entry => entry.word.lemma)
    let target_placement: 'DIALOGUE' | 'OPTIONS' | null = null
    if (kind === 'CONTEXT_TO_WORD') content = `In this situation: “${strip(hide(example)).replace('_', '…')}” — ${definition}.`
    if (kind === 'CLOZE_TO_WORD') {
      content = hide(example).includes('_') ? hide(example) : `To express “${definition}”, use _.`
      correctText = example.match(/<t\b[^>]*>(.*?)<\/t>/i)?.[1] ?? word.lemma
    }
    if (kind === 'WORD_TO_DEFINITION') {
      content = `<t inf="base">${word.lemma}</t>`; correctText = definition
      wrongTexts = distractors.map(entry => entry.sense.definition?.content ?? `another meaning of ${entry.word.lemma}`)
    }
    if (kind === 'WORD_TO_USAGE') {
      content = `<t inf="base">${word.lemma}</t> — ${definition}`; correctText = example
      wrongTexts = distractors.map(entry => entry.sense.examples[0]?.content ?? `They discussed ${entry.word.lemma}.`)
    }
    if (kind === 'DIALOGUE_COMPLETION') {
      target_placement = variant % 2 ? 'OPTIONS' : 'DIALOGUE'
      content = [
        { speaker: variant % 2 ? 'Maya' : 'Alex', text: target_placement === 'DIALOGUE' ? `I saw this today: ${example}` : `I need an expression meaning “${definition}”.` },
        { speaker: variant % 2 ? 'Noah' : 'Sam', text: null },
      ]
      correctText = target_placement === 'OPTIONS' ? `I’d use <t inf="base">${word.lemma}</t> to mean ${definition}.` : `Yes, that describes ${definition}.`
      wrongTexts = distractors.map(entry => target_placement === 'OPTIONS' ? `I’d use <t inf="base">${word.lemma}</t> to mean ${entry.sense.definition?.content ?? entry.word.lemma}.` : `No, it means ${entry.sense.definition?.content ?? entry.word.lemma}.`)
    }
    if (kind === 'MEANING_IN_CONTEXT') {
      content = example; correctText = definition
      wrongTexts = distractors.map(entry => entry.sense.definition?.content ?? `another meaning of ${entry.word.lemma}`)
    }
    const correct = option(`${qid}:c`, correctText, `This matches “${definition}”.`)
    const wrong = wrongTexts.map((value, index) => option(`${qid}:${index}`, value, `This expresses a different meaning.`))
    const pool = [correct, ...wrong], rotate = variant % pool.length
    const options = [...pool.slice(rotate), ...pool.slice(0, rotate)]
    return { question: { id: qid, sense_id: sense.id, theme_id: null, question_type: kind, content, correct, distractors: wrong,
      correct_alternatives: [], target_placement }, format: 'SINGLE_CHOICE', level: 1, options }
  }
  function selectFormats(kinds: QuestionType[], preferences: LearningSettings, reason: PreparedBundle['reason']): AnswerFormat[] {
    const formats = kinds.map(kind => {
      const available = pairs[kind].filter(format => preferences.formats.includes(format))
      if (!available.length) throw new HomeApiError(422, 'infeasible_learning_preferences')
      return available.includes('SINGLE_CHOICE') ? 'SINGLE_CHOICE' : available[0]
    })
    if (reason !== 'NEW' && preferences.formats.includes('SINGLE_CHOICE')) {
      for (const format of ['SHORT_ANSWER', 'SINGLE_WORD'] as const) {
        const index = kinds.findIndex((kind, index) => formats[index] === 'SINGLE_CHOICE' && pairs[kind].includes(format) && preferences.formats.includes(format))
        if (index !== -1) formats[index] = format
      }
    }
    return formats
  }
  function prepare(input: { node_id: string; selection: 'DUE' | 'NEW' | 'AUTO'; max_sense_count?: number }, preferences: LearningSettings): PreparedSession {
    library.details(input.node_id)
    const target = input.max_sense_count ?? preferences.max_sense_count, k = preferences.questions_per_sense
    if (target < 1 || target * k > 100) throw new HomeApiError(422, 'invalid_preparation')
    const all: Meaning[] = []
    let pageCursor: string | undefined
    do {
      const page = library.meanings(input.node_id, { state: 'ALL', limit: 100, cursor: pageCursor })
      all.push(...page.senses); pageCursor = page.next_cursor ?? undefined
    } while (pageCursor)
    const due = all.filter(item => item.learning?.state === 'DUE'), fresh = all.filter(item => item.learning?.state === 'NEW')
    const early = all.filter(item => item.learning?.state === 'NOT_YET_DUE')
    const selected = (input.selection === 'DUE' ? due : input.selection === 'NEW' ? fresh : [...due, ...fresh, ...early]).slice(0, target)
    const enabled = types.filter(kind => preferences.question_types.includes(kind) && pairs[kind].some(format => preferences.formats.includes(format)))
    if (!enabled.length) throw new HomeApiError(422, 'infeasible_learning_preferences')
    const bundles = selected.map(item => {
      const entry = bySense.get(item.sense_id)
      if (!entry) throw new HomeApiError(409, 'learning_content_changed')
      const reason = item.learning!.state
      const kinds = Array.from({ length: k }, (_, index) => enabled[(cursor + entry.sense.id + index) % enabled.length])
      const formats = selectFormats(kinds, preferences, reason)
      const questions = kinds.map((kind, index) => {
        const question = build(entry.word, entry.sense, kind, (cursor + index) % 8)
        const format = formats[index]
        return { ...question, format, level: Number(db.account.learning_options.pairs.find(pair => pair.question_type === kind && pair.format === format)?.level ?? 1) }
      })
      return { sense: entry.sense, reason, questions }
    })
    cursor++
    return parsePreparation({ node_id: input.node_id, selection: input.selection, max_sense_count: target, actual_sense_count: bundles.length,
      actual_question_count: bundles.length * k, preferences, bundles })
  }
  function grade(input: { question_id: number; format: AnswerFormat; answer: string }): GradeResult {
    // ponytail: preview grading uses lexical heuristics; live mode delegates semantic grading to Lexi.
    if (input.format === 'SINGLE_CHOICE') throw new HomeApiError(422, 'invalid_grade_request')
    const senseId = Math.floor(input.question_id / 1000), entry = bySense.get(senseId)
    if (!entry) throw new HomeApiError(404, 'question_not_found')
    const kind = types[Math.floor((input.question_id % 1000) / 100)], variant = input.question_id % 100 - 1
    if (!kind || variant < 0 || variant > 7 || !pairs[kind].includes(input.format)) throw new HomeApiError(422, 'unsupported_question_format')
    const answer = normalize(input.answer), word = normalize(entry.word.lemma), definition = normalize(entry.sense.definition?.content ?? '')
    if (!answer) throw new HomeApiError(422, 'invalid_grade_request')
    if (input.format === 'SINGLE_WORD') {
      const expected = normalize(build(entry.word, entry.sense, kind, variant).question.correct.content)
      const matched = entries.find(item => normalize(item.word.lemma) === answer)
      const spelling_error = answer !== expected && Math.abs(answer.length - expected.length) <= 1 && answer.slice(0, 2) === expected.slice(0, 2) && !matched
      return parseGrade({ task_fit: answer === expected || spelling_error || Boolean(matched), spelling_error,
        sense_id: spelling_error ? null : answer === expected ? senseId : matched?.sense.id ?? null })
    }
    if (kind === 'WORD_TO_DEFINITION') {
      const terms = definition.split(/\W+/).filter(term => term.length > 4)
      const hits = terms.filter(term => answer.includes(term)).length
      return parseGrade({ sense_id: hits ? senseId : null, accuracy: hits >= Math.min(2, terms.length) ? 'ACCURATE' : hits ? 'MIXED' : null,
        coverage: hits >= Math.min(2, terms.length) ? 'SUFFICIENT' : hits ? 'PARTIAL' : null })
    }
    const used = answer.includes(word)
    const meaning = used && (definition.split(/\W+/).some(term => term.length > 4 && answer.includes(term)) || answer.length > word.length + 25) ? 'CORRECT' : used ? 'APPROXIMATE' : null
    return parseGrade({ used, meaning, form: used ? 'CORRECT' : null, construction: used ? true : null,
      collocation: used ? 'ACCEPTABLE' : null, appropriacy: used ? 'APPROPRIATE' : null })
  }
  function review(input: { results: { sense_id: number; rating: Rating }[]; key: string }): ReviewBatchResult {
    const body = JSON.stringify(input.results), previous = receipts.get(input.key)
    if (previous) { if (previous.body !== body) throw new HomeApiError(409, 'review_batch_conflict'); return previous.result }
    if (!input.results.length || input.results.length > 100 || new Set(input.results.map(item => item.sense_id)).size !== input.results.length) throw new HomeApiError(422, 'invalid_review_batch')
    if (input.results.some(item => !bySense.has(item.sense_id))) throw new HomeApiError(422, 'sense_not_found')
    const accepted = now().toISOString(), date = accepted.slice(0, 10)
    const results = input.results.map(item => {
      const state = db.library.new_sense_ids.includes(item.sense_id) ? 'NEW' : db.library.due_sense_ids.includes(item.sense_id) ? 'DUE' : 'NOT_YET_DUE'
      const applied = state !== 'NOT_YET_DUE' || item.rating === 'AGAIN'
      if (applied) library.setLearning(item.sense_id, item.rating)
      return { ...item, applied, accepted_at: accepted, due_after: new Date(now().getTime() +
        (applied ? item.rating === 'AGAIN' ? 1 : item.rating === 'HARD' ? 2 : item.rating === 'GOOD' ? 5 : 10 : 3) * 86400000).toISOString() }
    })
    const result = parseReviewBatch({ accepted_at: accepted, activity_day: date, results })
    receipts.set(input.key, { body, result })
    return result
  }
  return { prepare, grade, review }
}
