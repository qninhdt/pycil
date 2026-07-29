import { readFileSync } from "node:fs"

import { test as base, expect, type Page } from "@playwright/test"

import { seedDeckFromSenseIds } from "./api"
import { mintSessionState, type MintedSession } from "./auth"
import { FIXTURE_PATH, specIdentityEmail } from "./env"
import { markSensesDue } from "./schedule"
import type { E2EFixture } from "./types"

/**
 * The seeded fixture, read from disk.
 *
 * Global setup runs in its own process, so nothing it puts on `globalThis`
 * survives into a worker. The file is the handoff.
 */
export function readFixture(): E2EFixture {
  try {
    return JSON.parse(readFileSync(FIXTURE_PATH, "utf8")) as E2EFixture
  } catch (error) {
    throw new Error(
      `Could not read the E2E fixture at ${FIXTURE_PATH}. ` +
        `Global setup must run before the specs. Original error: ${String(error)}`,
    )
  }
}

interface Fixtures {
  fixture: E2EFixture
  /** A page with no session cookie, for the anonymous-read specs. */
  anonymousPage: Page
  /** A learner of this spec's own, with its own deck. */
  learner: Learner
  /** A page signed in as `learner` rather than as the run-wide identity. */
  learnerPage: Page
  /**
   * The same learner, but with a review history: senses due, mastery high.
   *
   * Its own fixture rather than an option on `learner` because the schedule has to
   * be seeded *before* the browser opens — the launch screen reads what is due on
   * load, so a page created first would show an empty deck.
   */
  returningLearner: Learner
  /** A page signed in as `returningLearner`. */
  returningLearnerPage: Page
}

/** A per-spec learner: its own identity, its own deck, the run's shared senses. */
export interface Learner {
  email: string
  userId: string
  token: string
  folderId: string
  deckId: string
  deckName: string
  senseIds: number[]
  /** This learner's sealed cookie, ready for `browser.newContext`. */
  storageState: MintedSession["storageState"]
}

export const test = base.extend<Fixtures>({
  fixture: async ({}, use: (value: E2EFixture) => Promise<void>) => {
    await use(readFixture())
  },

  /**
   * A learner nobody else has touched, built fresh for the spec that asks for it.
   *
   * Scheduling state is keyed `(user_id, sense_id)`, so the first spec to study a
   * deck leaves every sense scheduled for a later day and the next spec opens on
   * "Nothing due right now". Sharing one learner therefore makes the study specs
   * order-dependent: whichever runs first passes, and the rest fail on a stale
   * schedule that looks exactly like a planner bug.
   *
   * This is cheap because the expensive artefacts are global. Senses are written
   * once by the generation path and prepared questions are keyed by word and level
   * with the owner explicitly dropped (`jobs/generate_question.py`), so a new
   * learner adding the run's sense ids to a deck of its own inherits warm supply
   * and pays no model call. Verified against the running stack: a brand-new
   * identity retrieved a prepared assessment immediately.
   */
  learner: async ({}, use, testInfo) => {
    const fixture = readFixture()
    const email = specIdentityEmail(testInfo.title)
    const minted = await mintSessionState(email)
    const { folder, deck } = await seedDeckFromSenseIds(
      minted.accessToken,
      fixture.senseIds,
      testInfo.title.slice(0, 40),
    )
    await use({
      email: minted.user.email,
      userId: minted.user.id,
      token: minted.accessToken,
      folderId: folder.id,
      deckId: deck.id,
      deckName: deck.name,
      senseIds: fixture.senseIds,
      storageState: minted.storageState,
    })
  },

  /**
   * A browser signed in as this spec's own learner.
   *
   * Built here rather than through the project's `storageState`, which holds the
   * run-wide identity: a spec that needs an untouched schedule needs the cookie to
   * match the learner whose deck it is about to study.
   */
  learnerPage: async ({ browser, learner }, use) => {
    // `mintSessionState` already sealed a cookie for exactly this learner, so it is
    // reused rather than re-sealed: sealing twice would mean two envelopes that have
    // to agree, and the second one drifting is a failure nobody would look for here.
    const context = await browser.newContext({ storageState: learner.storageState })
    const page = await context.newPage()
    await use(page)
    await context.close()
  },

  /**
   * A learner who has studied this deck before and done well at it.
   *
   * The difference from `learner` is the review history, and it is what makes the
   * rubric-graded path reachable at all. Free-text questions only exist at
   * difficulty levels 3 and 4, and a level above the assessment floor is only
   * requested for a sense whose purpose is `due`: acquisition pins every checkpoint
   * to `ASSESSMENT_FLOOR` (`learning/planning.py`). So a deck of new words serves
   * nothing but single-choice, and the SSE grading path — task id, deferred verdict,
   * reload mid-grade — could never be exercised by `learner`.
   *
   * High mastery rather than merely due: the level profiles in `learning/policy.py`
   * only give levels 3 and 4 real weight from the 56-80 band up, so a low-mastery
   * due sense would still usually draw level 1 and the spec would be a coin flip.
   */
  returningLearner: async ({ learner }, use) => {
    await markSensesDue(learner.userId, learner.senseIds)
    await use(learner)
  },

  /**
   * A browser signed in as the returning learner.
   *
   * Depends on `returningLearner` rather than `learner` so the schedule is already
   * fast-forwarded before the first navigation: the launch screen reads what is due
   * on load, and a page opened first would show an empty deck.
   */
  returningLearnerPage: async ({ browser, returningLearner }, use) => {
    const context = await browser.newContext({
      storageState: returningLearner.storageState,
    })
    const page = await context.newPage()
    await use(page)
    await context.close()
  },

  /**
   * A context explicitly built with no storage state.
   *
   * `test.use({ storageState: undefined })` would inherit the project default in
   * some configurations, and an anonymous spec that is quietly signed in asserts
   * nothing. Building the context here makes the absence explicit.
   */
  anonymousPage: async ({ browser }, use) => {
    const context = await browser.newContext({ storageState: undefined })
    const page = await context.newPage()
    await use(page)
    await context.close()
  },
})

export { expect }
