/**
 * Dictionary content: senses, their detail view, and word search.
 *
 * Derived from `reports/v1-openapi-snapshot.json`.
 */

/**
 * A sense as it appears in a deck list or a search result.
 *
 * `word` is nullable because the upstream dictionary can regenerate a sense away
 * while local learning state survives. A deck row must therefore be renderable
 * with a definition and no headword.
 *
 * The learning fields are present only when the caller owns state for the sense,
 * which is why they are all optional: an anonymous reader of a public deck gets
 * the content and none of the progress.
 */
export interface SenseContent {
  definition: string
  tier: string
  senseId?: number | null
  word?: string | null
  wordId?: number | null
  pos?: string | null
  cefrLevel?: string | null
  examples?: string[]
  mastery?: number | null
  /** 1-5, matching the mastery bands in `lib/design/mastery.ts`. */
  masteryStage?: number | null
  masteryStageName?: string | null
  status?: string | null
  reviewCount?: number | null
  lapseCount?: number | null
  nextReviewDate?: string | null
}

export interface SenseForm {
  /** The inflection label, e.g. "past participle". */
  inf: string
  surface: string
}

export interface SenseReference {
  source: string
  sourceRef: string
}

/**
 * A relation to another sense.
 *
 * `toSenseId` is null when the target word exists but the specific sense has not
 * been disambiguated, which is what `wsdState` reports.
 */
export interface SenseRelation {
  relType: string
  toWordId: number
  toWordDisplay: string
  toWordStatus: string
  wsdState: string
  toSenseId?: number | null
  toSenseGloss?: string | null
}

/** The full sense record behind `/w/[senseId]`. */
export interface SenseDetail {
  senseId: number
  definition: string
  tier: string
  word?: string | null
  wordId?: number | null
  pos?: string | null
  cefrLevel?: string | null
  guideword?: string | null
  /** Phonetic transcription. Text only: there is no audio in this product. */
  ipaUk?: string | null
  ipaUs?: string | null
  examples?: string[]
  collocations?: string[]
  grammar?: string[]
  forms?: SenseForm[]
  references?: SenseReference[]
  relations?: SenseRelation[]
  register?: string | null
  connotation?: string | null
  domain?: string | null
  usageNote?: string | null
}

export interface WordSearchResult {
  display: string
  entryType?: string | null
  score?: number
  wordId?: number | null
  cambridgeId?: number | null
  gloss?: string | null
  pos?: string | null
  senses?: SenseContent[]
}

/** The receipt for an asynchronous word generation. */
export interface GenerationCreated {
  taskId: string
}

/**
 * The result of adding a sense to a deck.
 *
 * The API returns a bare `{id, senseId}` dict rather than a declared model, so
 * the OpenAPI document describes it only as an object of integers. This shape is
 * read from the route itself.
 */
export interface SenseAdded {
  id: number
  senseId: number
}
