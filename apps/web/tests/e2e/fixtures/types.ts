import type { SenseContent } from "./api"

/**
 * The seeded fixture, shared between global setup and the specs.
 *
 * It lives in its own module on purpose. Global setup is a default-export module
 * that Playwright *executes*; importing a type from it would make every spec file
 * pull that module into its own graph, and with it the compose calls and the
 * network I/O at its top level. A plain type module has no such cost.
 */
export interface E2EFixture {
  user: { id: string; email: string }
  /** A private folder owned by the E2E identity. */
  folderId: string
  /** A private deck inside that folder, seeded and with supply warmed. */
  deckId: string
  /** A deck published for the anonymous-read specs. */
  publicDeckId: string
  /**
   * The names the API stored, carried alongside the ids.
   *
   * A spec asserting on a heading or a breadcrumb needs the text, and re-deriving
   * it from the timestamp the setup used would be two places agreeing by accident.
   * These are the values the server actually holds.
   */
  folderName: string
  deckName: string
  publicDeckName: string
  /** Senses in the private deck, in the order they were added. */
  senses: SenseContent[]
  /**
   * Just the ids from `senses`, for building a per-spec deck.
   *
   * Generated senses are global — they live in Lexi's own store and are visible to
   * any identity, verified against the running stack — so a fresh learner can add
   * these exact ids to a deck of its own and inherit the supply this run already
   * warmed for them.
   */
  senseIds: number[]
  /** A sense id that resolves through `/w/[senseId]` for the public-read spec. */
  publicSenseId: number
  /** Words seeded into the reference library, for the palette search spec. */
  seededWords: string[]
  /**
   * True when an assessment was observed as retrievable before the run started.
   *
   * The study specs branch on this rather than assuming it. Assessments are built
   * by a live model, and a stack configured without a working `LEXI_LLM_*`
   * endpoint can serve exposure cards perfectly well while never producing a
   * single graded question — so the difference has to be reported, not guessed.
   */
  supplyWarmed: boolean
}
