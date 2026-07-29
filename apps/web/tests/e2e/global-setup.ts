import { mkdir, writeFile } from "node:fs/promises"
import { dirname } from "node:path"

import type { FullConfig } from "@playwright/test"

import {
  addSenseToDeck,
  apiCall,
  createDeck,
  createFolder,
  findMaterialisedSenses,
  publishNode,
  waitFor,
  warmQuestionSupply,
  type SenseContent,
} from "./fixtures/api"
import { assertNoDevAuthRoute, mintSessionState, type MintedSession } from "./fixtures/auth"
import { AUTH_STATE_PATH, FIXTURE_PATH, loadE2EEnv } from "./fixtures/env"
import type { E2EFixture } from "./fixtures/types"

/**
 * Everything the suite needs, built once against the live stack.
 *
 * Three jobs, in order, because each depends on the last: prove the auth seam has
 * not grown an HTTP surface, mint and seal a session, then seed real content
 * through the real API.
 *
 * Seeding is deliberately not done through the UI. Driving four word generations
 * and a deck build through the browser would make every spec's setup depend on the
 * screens under test, so a broken palette would fail the study specs too and the
 * report would not say which thing was actually wrong.
 */

/**
 * The words the fixture is built from.
 *
 * They share topic tags on purpose, and that is load-bearing rather than
 * cosmetic. Multiple-choice distractors come from a two-rung ladder: semantic
 * neighbours, which need the vector backend this stack deliberately leaves off
 * (`LEXI_VECTOR_BACKEND=none`), and then words sharing a topic tag. With the first
 * rung off, an MCQ can only be built when *other* words in the library share a tag
 * with the target — `_mcq_question` returns null below one distractor. A fixture of
 * unrelated words therefore yields zero assessments, silently, and every study
 * assertion would wait forever on supply that can never arrive.
 */
const FIXTURE_WORDS = ["resilient", "tenacious", "stoic", "brittle"] as const

/**
 * Words materialised into the library but never added to the deck.
 *
 * The palette spec adds one of these, so it has to be findable *and* absent from
 * the deck: adding a sense that is already there would assert nothing.
 */
const SEARCHABLE_WORDS = ["placid", "volatile"] as const

async function writeJson(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true })
  await writeFile(path, JSON.stringify(value, null, 2), "utf8")
}

/**
 * Resolves a word to its senses, generating it first if the library lacks it.
 *
 * The reference dataset is a Cambridge *search index*, not a populated sense
 * store. A hit for a word nobody has generated comes back with `wordId: null` and
 * an empty `senses` array, because senses live in Lexi's own database and are
 * written only by the generation path. So a fixture cannot search-and-add; it has
 * to ensure the entry exists, which means driving a live model and waiting.
 *
 * The wait is on the observable condition — search reporting materialised senses —
 * rather than on the task status, because materialised senses are what the deck
 * actually needs. A succeeded task whose senses are not yet readable would satisfy
 * a status check and then fail the add.
 */
async function resolveOrGenerate(token: string, word: string): Promise<SenseContent[]> {
  const existing = await findMaterialisedSenses(token, word)
  if (existing.length > 0) return existing

  // 202 is the happy path. 409 and 429 are the durable-generation guards: the word
  // is already in flight, or this identity has spent its hourly budget. Neither is
  // a fixture failure on its own, because the poll below is what decides — an
  // in-flight generation from an earlier run still lands.
  const { status } = await apiCall<{ taskId: string }>("/v1/word-generations", {
    method: "POST",
    token,
    body: { query: word },
    expectStatus: [202, 409, 429],
  })
  if (status !== 202) {
    console.warn(
      `[e2e] generation for "${word}" was refused with ${status}; ` +
        "polling search in case it is already in flight",
    )
  }

  return waitFor(
    `"${word}" to be materialised into the library by the worker`,
    () => findMaterialisedSenses(token, word),
    (senses) => senses.length > 0,
    { timeoutMs: 300_000, intervalMs: 3_000 },
  )
}

export default async function globalSetup(config: FullConfig): Promise<void> {
  void config
  const env = loadE2EEnv()

  // First, before anything is seeded: the seam this suite rests on must not have
  // grown an HTTP surface. Cheap, and it fails the whole run rather than one spec.
  await assertNoDevAuthRoute()

  console.log(`[e2e] stack: ${env.baseURL} (api ${env.apiURL}) as ${env.identityEmail}`)

  const session: MintedSession = await mintSessionState()
  await writeJson(AUTH_STATE_PATH, session.storageState)
  console.log(`[e2e] sealed a session cookie for ${session.user.email}`)

  const token = session.accessToken
  const stamp = Date.now().toString(36)

  // --- library structure ------------------------------------------------------
  //
  // Timestamped so a re-run neither collides with nor silently reuses the previous
  // run's tree.
  const folder = await createFolder(token, `E2E folder ${stamp}`)
  const deck = await createDeck(token, `E2E deck ${stamp}`, folder.id)
  const publicDeck = await createDeck(token, `E2E public deck ${stamp}`, folder.id)

  // --- content ---------------------------------------------------------------
  const senses: SenseContent[] = []
  for (const word of FIXTURE_WORDS) {
    const resolved = await resolveOrGenerate(token, word)
    // One sense per word rather than every sense of one word. Four senses drawn
    // from four different headwords give the planner four independent items, which
    // is what makes a round boundary reachable in a short session.
    const sense = resolved.find((item) => typeof item.senseId === "number")
    if (!sense || typeof sense.senseId !== "number") {
      throw new Error(`"${word}" materialised no sense carrying an id`)
    }
    await addSenseToDeck(token, deck.id, sense.senseId)
    senses.push(sense)
    console.log(`[e2e] deck += ${word} (sense ${sense.senseId})`)
  }

  // The anonymous-read specs need one published deck with something in it.
  const publicSense = senses[0]
  if (typeof publicSense.senseId !== "number") {
    throw new Error("the first fixture sense carries no id")
  }
  await addSenseToDeck(token, publicDeck.id, publicSense.senseId)
  await publishNode(token, publicDeck.id)

  const seededWords: string[] = []
  for (const word of SEARCHABLE_WORDS) {
    try {
      await resolveOrGenerate(token, word)
      seededWords.push(word)
    } catch (error) {
      // A searchable word is a convenience for one spec, not a precondition for
      // the suite. That spec skips explicitly when the list is empty.
      console.warn(`[e2e] could not materialise searchable word "${word}": ${String(error)}`)
    }
  }

  // --- supply ----------------------------------------------------------------
  //
  // Warmed here so model latency sits in setup rather than inside an assertion.
  // A failure is recorded rather than thrown: the study specs skip explicitly on
  // `supplyWarmed: false`, which is far more useful than every study assertion
  // timing out with no stated reason.
  let supplyWarmed = false
  try {
    await warmQuestionSupply(token, deck.id)
    supplyWarmed = true
    console.log("[e2e] question supply warmed: an assessment is retrievable")
  } catch (error) {
    console.warn(`[e2e] supply warm-up did not complete: ${String(error)}`)
  }

  const fixture: E2EFixture = {
    user: { id: session.user.id, email: session.user.email },
    folderId: folder.id,
    deckId: deck.id,
    publicDeckId: publicDeck.id,
    folderName: folder.name,
    deckName: deck.name,
    publicDeckName: publicDeck.name,
    senses,
    // Lifted out of `senses` so a per-spec learner can rebuild an equivalent deck
    // of its own without re-searching the library. These ids are global: senses are
    // written once by the generation path and belong to no user, which is what
    // makes per-spec isolation cost a deck rather than a round of generation.
    senseIds: senses
      .map((sense) => sense.senseId)
      .filter((id): id is number => typeof id === "number"),
    publicSenseId: publicSense.senseId,
    seededWords,
    supplyWarmed,
  }
  await writeJson(FIXTURE_PATH, fixture)
  console.log(
    `[e2e] fixture ready: deck ${deck.id} with ${senses.length} senses, ` +
      `supply ${supplyWarmed ? "warmed" : "NOT warmed"}`,
  )
}
