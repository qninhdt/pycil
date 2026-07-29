/**
 * Study: sessions, the `/next` question union, and grading.
 *
 * Derived from `reports/v1-openapi-snapshot.json`, with two corrections the
 * document cannot express:
 *
 * 1. The `/next` discriminator is advertised as `propertyName: "render_format"`,
 *    but the property actually serialised is `renderFormat`. Pydantic builds the
 *    discriminator from the field name while the response uses the alias, so a
 *    generator that trusts the document would key on a property that is never
 *    present.
 * 2. Every `payload` is declared as an open object. The real shapes come from the
 *    upstream dictionary and are typed here per format, keeping the snake_case
 *    keys it actually sends.
 */

/** How a question is meant to be answered. Exposure is shown, not graded. */
export type InteractionMode = "exposure" | "assessment"

export type RenderFormat = "flashcard" | "single_choice" | "text_span" | "free_text"

/**
 * The five states `/next` can return.
 *
 * `ready` is further discriminated by `renderFormat`. The other four carry no
 * question: they say why there isn't one.
 */
export type NextQuestionState =
  | "ready"
  | "break"
  | "preparing"
  | "waiting"
  | "exhausted"

/**
 * Payloads, with the upstream dictionary's own key casing.
 *
 * These keys are snake_case in the response because the API passes the
 * dictionary's render contract through verbatim rather than restating it. That is
 * deliberate on their side, so the types say so instead of pretending otherwise.
 * No case transform may be applied to a payload.
 */
export interface FlashcardPayload {
  word: string
  definition: string
  pos: string | null
  example: string | null
  ipa_uk: string | null
  ipa_us: string | null
}

export interface SingleChoicePayload {
  stem: string
  /** Carries no correct-answer marker; the verdict arrives only from grading. */
  options: string[]
}

export interface TextSpanPayload {
  stem_with_blank: string
  word_bank: string[]
}

export interface FreeTextPayload {
  prompt: string
}

/** Fields every ready question carries, whatever its format. */
interface ReadyQuestionBase {
  state: "ready"
  /**
   * Null for an exposure card. Exposure is not assessed, so it has no answerable
   * question id, and submitting one is rejected.
   */
  questionId: number | null
  senseId: number
  interactionMode: InteractionMode
  /** The level asked for, and the level actually served. */
  requestedLevel: number
  servedLevel: number
  /** True when the served level had to differ from the requested one. */
  isFallback: boolean
}

export interface FlashcardReady extends ReadyQuestionBase {
  renderFormat: "flashcard"
  payload: FlashcardPayload
}

export interface SingleChoiceReady extends ReadyQuestionBase {
  renderFormat: "single_choice"
  payload: SingleChoicePayload
}

export interface TextSpanReady extends ReadyQuestionBase {
  renderFormat: "text_span"
  payload: TextSpanPayload
}

export interface FreeTextReady extends ReadyQuestionBase {
  renderFormat: "free_text"
  payload: FreeTextPayload
}

export type ReadyQuestion =
  | FlashcardReady
  | SingleChoiceReady
  | TextSpanReady
  | FreeTextReady

/** The round is full. The next call advances into a fresh one. */
export interface NextQuestionBreak {
  state: "break"
  roundIndex: number
}

/** Questions are being generated. Poll again, do not resubmit anything. */
export interface NextQuestionPreparing {
  state: "preparing"
}

/** A grade is outstanding and must settle before the next question. */
export interface NextQuestionWaiting {
  state: "waiting"
}

/** Nothing left to study in this session. */
export interface NextQuestionExhausted {
  state: "exhausted"
}

export type NextQuestion =
  | ReadyQuestion
  | NextQuestionBreak
  | NextQuestionPreparing
  | NextQuestionWaiting
  | NextQuestionExhausted

export interface SessionStart {
  nodeId: string
}

export interface SessionCreated {
  sessionId: string
  nodeId: string
  admittedCount: number
  expiresAt: string
  /** "ready" when anything was admitted, "exhausted" when nothing was. */
  firstState: "ready" | "exhausted"
}

/** Where one admitted sense stands. Present only while a session is live. */
export interface SessionSenseProgress {
  senseId: number
  /** Why the sense is in this session: newly introduced, or due for review. */
  purpose: string
  passed: number
  required: number
  /** A formatted score, not a number: the API renders it for display. */
  score: string
  exposed: boolean
  awaitingGrade: boolean
  terminal: boolean
  terminalReason: string
}

/**
 * One session, live or finished.
 *
 * `status` decides which half of this shape is populated: a live session is
 * served from the round store and carries round counters and per-sense progress;
 * a completed one carries only the summary totals.
 */
export interface SessionState {
  sessionId: string
  status: "live" | "completed"
  nodeId?: string | null
  roundIndex?: number | null
  roundCount?: number | null
  maxPerRound?: number | null
  expiresAt?: string | null
  senses?: SessionSenseProgress[]
  sensesAdmitted?: number
  sensesCompleted?: number
  sensesExhausted?: number
  answersTotal?: number
  answersCorrect?: number
  roundsUsed?: number
  completedAt?: string | null
}

/**
 * How a session is shaped, per learner.
 *
 * These belong to the account rather than to a deck. Held per deck, the same person
 * got a different session length depending on which deck they opened, and a session
 * started on a folder ignored them entirely because a folder has no settings of its
 * own — so the configured values applied roughly half the time.
 *
 * A read never comes back empty. Someone who has never opened Settings has no stored
 * row, and the API resolves that to the policy defaults so no client has to
 * reimplement them in order to show a number.
 */
export interface LearningSettings {
  targetWordsPerSession: number
  maxQuestionsPerRound: number
}

export interface AnswerSubmission {
  sessionId: string
  /** Numeric. An exposure card has no id and cannot be submitted. */
  questionId: number
  answer: string
}

/**
 * The answer disclosure, released only after grading.
 *
 * Which variant arrives follows the question's format: a choice question reveals
 * an index, a span reveals the accepted text, a rubric-graded answer reveals only
 * feedback. Every field is optional because the shape is not declared in the
 * contract, so a consumer must narrow before reading.
 *
 * **snake_case, like the question payloads and for the same reason.** The API
 * builds this with `asdict()` over the dictionary's own reveal dataclass and puts
 * the result in a bare `dict` field, so no alias applies to the keys inside — they
 * arrive exactly as the upstream contract names them. The OpenAPI document
 * declares the field `additionalProperties: true` and therefore cannot show this,
 * which is why it is stated here: a camelCase reading compiles cleanly and then
 * finds `undefined` at runtime, silently rendering no answer at all.
 */
export interface Reveal {
  correct_index?: number
  correct_option?: string
  correct_answer?: string
  accepted_forms?: string[]
  feedback?: string | null
}

/**
 * The result of an answer.
 *
 * Two modes. `graded` carries the verdict, the reveal, and the mastery
 * transition inline. `pending` carries a `taskId` instead: the grade is running
 * asynchronously and settles through a realtime snapshot.
 */
export interface GradeResult {
  responseId: string
  gradeStatus: "graded" | "pending"
  senseId: number
  renderFormat: RenderFormat
  /** Present only when `gradeStatus` is "pending". */
  taskId?: string | null
  isCorrect?: boolean | null
  gradeScore?: number | null
  gradeFeedback?: string | null
  reveal?: Reveal | null
  masteryBefore?: number | null
  masteryAfter?: number | null
}

/**
 * Exhaustiveness guard for a discriminated union.
 *
 * Calling this in a `default` branch turns an unhandled variant into a compile
 * error. Without it, a sixth `/next` state would fall through at runtime and the
 * study screen would render nothing with no indication why.
 */
export function assertNever(value: never): never {
  throw new Error(`unhandled variant: ${JSON.stringify(value)}`)
}
