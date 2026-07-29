import { apiBaseUrl } from "./env"

/**
 * The E2E fixture, built through the real API.
 *
 * No SQL and no direct writes to Redis. Every row this creates arrives through
 * the same endpoints the browser uses, so the fixture cannot drift into a state
 * the application could never produce — which is the failure mode that makes a
 * seeded suite pass while the product is broken.
 *
 * Waiting is on observable conditions only. There is no `sleep` anywhere in this
 * file: question supply is prepared asynchronously by the worker through a live
 * language model, so its latency is not something a constant can encode. Every
 * wait polls a real endpoint until it reports the state that was asked for, and
 * fails with what it saw instead of what it wanted.
 */

export interface ApiCallOptions {
  method?: string
  body?: unknown
  /** Absent for the anonymous reads that prove the public-link behaviour. */
  token?: string
  expectStatus?: number[]
}

export interface ApiResponse<T> {
  status: number
  body: T
}

/** One request to the API, with the failure text a caller can act on. */
export async function apiCall<T = unknown>(
  path: string,
  { method = "GET", body, token, expectStatus }: ApiCallOptions = {},
): Promise<ApiResponse<T>> {
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers["Content-Type"] = "application/json"

  const response = await fetch(`${apiBaseUrl()}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  })

  let parsed: unknown = null
  const text = await response.text()
  if (text) {
    try {
      parsed = JSON.parse(text)
    } catch {
      parsed = text
    }
  }

  if (expectStatus && !expectStatus.includes(response.status)) {
    throw new Error(
      `${method} ${path} returned ${response.status}, expected one of ` +
        `${expectStatus.join(", ")}. Body: ${JSON.stringify(parsed)}`,
    )
  }

  return { status: response.status, body: parsed as T }
}

export interface Node {
  id: string
  name: string
  type: string
  parentNodeId?: string | null
  visibility?: string
  itemCount?: number | null
}

export interface SenseContent {
  senseId?: number | null
  word?: string | null
  definition: string
  tier: string
  /**
   * The dictionary's example sentences, with the target word tagged.
   *
   * Carried because a cloze stem *is* one of these with the target blanked out, so
   * matching a stem back to its example is how a spec resolves the word a typed
   * gap-fill expects. The `<t inf="...">` markers are the upstream dictionary's own
   * and are passed through verbatim; anything reading these must strip them rather
   * than assume plain text.
   */
  examples?: string[] | null
}

export interface WordSearchResult {
  display: string
  wordId?: number | null
  senses?: SenseContent[]
}

/**
 * `NodeType` and `Visibility` are uppercase on the wire.
 *
 * They are `str` enums whose values are their names (`FOLDER`, not `folder`), and
 * FastAPI validates against the value. A lowercase string is a 422, so these are
 * named constants rather than inline literals — one place to be wrong, and the
 * type checker catches a typo at the call site.
 */
export const NODE_TYPE = {
  folder: "FOLDER",
  deck: "DECK",
  reference: "REFERENCE",
} as const

export const VISIBILITY = {
  private: "PRIVATE",
  public: "PUBLIC",
} as const

export async function createFolder(
  token: string,
  name: string,
  parentNodeId?: string,
): Promise<Node> {
  const { body } = await apiCall<Node>("/v1/nodes", {
    method: "POST",
    token,
    body: { type: NODE_TYPE.folder, name, parentNodeId: parentNodeId ?? null },
    expectStatus: [201],
  })
  return body
}

export async function createDeck(
  token: string,
  name: string,
  parentNodeId?: string,
): Promise<Node> {
  const { body } = await apiCall<Node>("/v1/nodes", {
    method: "POST",
    token,
    body: { type: NODE_TYPE.deck, name, parentNodeId: parentNodeId ?? null },
    expectStatus: [201],
  })
  return body
}

/**
 * Publishes a node so the anonymous-reader specs have something to read.
 *
 * `confirmSubtreePublication` is set because publishing a node that contains
 * others is a decision about all of them, and the API refuses to infer consent.
 */
export async function publishNode(token: string, nodeId: string): Promise<Node> {
  const { body } = await apiCall<Node>(`/v1/nodes/${nodeId}/visibility`, {
    method: "PATCH",
    token,
    body: { visibility: VISIBILITY.public, confirmSubtreePublication: true },
    expectStatus: [200],
  })
  return body
}

export async function addSenseToDeck(
  token: string,
  nodeId: string,
  senseId: number,
): Promise<void> {
  await apiCall(`/v1/decks/${nodeId}/senses`, {
    method: "POST",
    token,
    body: { senseId },
    expectStatus: [201],
  })
}

export async function deckItems(
  token: string | undefined,
  nodeId: string,
): Promise<SenseContent[]> {
  const { body } = await apiCall<SenseContent[]>(`/v1/decks/${nodeId}/items`, {
    token,
    expectStatus: [200],
  })
  return body
}

/**
 * Searches for a word that already has materialised senses.
 *
 * The reference dataset is a Cambridge index, not a populated sense store: a
 * search hit for a word nobody has generated yet carries `wordId: null` and an
 * empty `senses` array, because the senses live in Lexi's own database and are
 * written by the generation path. So a fixture cannot assume a search result is
 * usable — it has to check, which is what this returns.
 */
export async function findMaterialisedSenses(
  token: string,
  query: string,
): Promise<SenseContent[]> {
  const { body } = await apiCall<WordSearchResult[]>(
    `/v1/words/search?q=${encodeURIComponent(query)}`,
    { token, expectStatus: [200] },
  )
  for (const result of body) {
    const senses = (result.senses ?? []).filter(
      (sense) => typeof sense.senseId === "number",
    )
    if (senses.length > 0) return senses
  }
  return []
}

/**
 * Polls until `predicate` holds, then returns the value that satisfied it.
 *
 * The failure message carries the last value seen. A wait that only reports
 * "timed out" forces the next reader to reproduce the run to learn anything.
 */
export async function waitFor<T>(
  describe: string,
  read: () => Promise<T>,
  predicate: (value: T) => boolean,
  { timeoutMs = 120_000, intervalMs = 2_000 }: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<T> {
  const deadline = Date.now() + timeoutMs
  let last: T | undefined
  let lastError: unknown
  while (Date.now() < deadline) {
    try {
      last = await read()
      if (predicate(last)) return last
      lastError = undefined
    } catch (error) {
      lastError = error
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  const seen = lastError
    ? `last error: ${lastError instanceof Error ? lastError.message : String(lastError)}`
    : `last value: ${JSON.stringify(last)}`
  throw new Error(`Timed out after ${timeoutMs}ms waiting for ${describe}. ${seen}`)
}

export interface SeededDeck {
  folder: Node
  deck: Node
  senseIds: number[]
}

/**
 * A folder containing a deck with real senses in it.
 *
 * Names carry a timestamp so a re-run does not collide with, or silently reuse,
 * the previous run's tree — the identity is stable for one run and unique across
 * runs.
 */
export async function seedDeck(
  token: string,
  { words, label }: { words: string[]; label: string },
): Promise<SeededDeck> {
  const stamp = Date.now().toString(36)
  const folder = await createFolder(token, `E2E ${label} folder ${stamp}`)
  const deck = await createDeck(token, `E2E ${label} deck ${stamp}`, folder.id)

  const senseIds: number[] = []
  for (const word of words) {
    const senses = await findMaterialisedSenses(token, word)
    for (const sense of senses.slice(0, 2)) {
      if (typeof sense.senseId !== "number") continue
      await addSenseToDeck(token, deck.id, sense.senseId)
      senseIds.push(sense.senseId)
    }
  }

  if (senseIds.length === 0) {
    throw new Error(
      `No materialised senses found for any of: ${words.join(", ")}.\n\n` +
        "The reference dataset indexes Cambridge headwords, but the senses a deck " +
        "holds are written by the generation path. Generate these words first " +
        "(POST /v1/word-generations) or seed the fixture with words that already " +
        "exist in Lexi's store.",
    )
  }

  return { folder, deck, senseIds }
}

/**
 * A deck of already-known senses, for a learner that needs its own copy.
 *
 * No search and no generation: the ids are passed in because they were resolved
 * once for the whole run. Senses are global — they live in Lexi's store, not under
 * an owner — so any identity can add these ids to a deck of its own, which is what
 * makes per-spec isolation cost four API calls instead of another model run.
 *
 * A deck rather than a shared one because node access is owner-or-public
 * (`hierarchy/access.py`), so one learner cannot open a session on another's
 * private deck. Publishing to share it would put the suite's isolation on a
 * visibility flag, and make the study specs depend on the publication path.
 */
export async function seedDeckFromSenseIds(
  token: string,
  senseIds: number[],
  label: string,
): Promise<{ folder: Node; deck: Node }> {
  const folder = await createFolder(token, `E2E ${label} folder`)
  const deck = await createDeck(token, `E2E ${label} deck`, folder.id)
  for (const senseId of senseIds) {
    await addSenseToDeck(token, deck.id, senseId)
  }
  return { folder, deck }
}

export interface SessionCreated {
  sessionId: string
  nodeId: string
  admittedCount: number
  firstState: "ready" | "exhausted"
}

export async function startSession(
  token: string,
  nodeId: string,
): Promise<SessionCreated> {
  const { body } = await apiCall<SessionCreated>("/v1/sessions", {
    method: "POST",
    token,
    body: { nodeId },
    expectStatus: [200],
  })
  return body
}

export interface SessionStateRead {
  sessionId: string
  status: "live" | "completed"
  nodeId?: string | null
  roundIndex?: number | null
  answersTotal: number
  answersCorrect: number
  sensesAdmitted: number
  sensesCompleted: number
}

/**
 * Reads a session's own record of what happened.
 *
 * A true read: it advances nothing and reserves nothing, unlike `/next`. That is what
 * makes it safe to call from a spec mid-session, and it is the only way to assert on
 * what the *server* recorded rather than on what a screen happens to be showing —
 * which matters for a grade that settled asynchronously, since the browser may have
 * moved on by the time the assertion runs.
 */
export async function readSessionState(
  token: string,
  sessionId: string,
): Promise<SessionStateRead> {
  const { body } = await apiCall<SessionStateRead>(`/v1/sessions/${sessionId}`, {
    token,
    expectStatus: [200],
  })
  return body
}

export interface NextQuestionResponse {
  state: "ready" | "break" | "preparing" | "waiting" | "exhausted"
  renderFormat?: string
  interactionMode?: string
  questionId?: number | null
  senseId?: number
}

/**
 * Warms question supply for a deck, off the browser's critical path.
 *
 * Creating a session enqueues `prepare_questions` for everything it admits, and
 * the worker then drives a live model to build them. That takes tens of seconds
 * per word, so doing it inside a spec makes the first assertion a test of model
 * latency rather than of the application.
 *
 * The session created here is **sacrificial**, and that is what makes driving
 * `/next` against it correct. `/next` mutates — it reserves a delivery, consumes
 * a round slot, and extends the exclusion set — so it must never be polled
 * against a session a spec is going to use. Against a session that is discarded
 * immediately, those consequences are discarded with it.
 *
 * Supply itself is not per-session: `prepare_questions` writes questions for a
 * `(sense, level)` pair into Lexi's own store, and reservations and exclusions
 * are held in the session's Redis namespace. So an assessment observed here
 * proves supply the spec's own fresh session can also retrieve.
 *
 * The wait ends on an assessment specifically, not on any `ready` state: every
 * sense has an exposure card available from the dictionary with no model
 * involved, so stopping at the first `ready` would return before a single
 * generated question existed.
 */
export async function warmQuestionSupply(
  token: string,
  nodeId: string,
  { timeoutMs = 420_000 }: { timeoutMs?: number } = {},
): Promise<void> {
  const sacrificial = await startSession(token, nodeId)
  if (sacrificial.firstState === "exhausted") {
    throw new Error(
      `Deck ${nodeId} admitted nothing, so no supply can be warmed. ` +
        "The deck has no senses, or every sense is already terminal for today.",
    )
  }

  await waitFor(
    "the worker to prepare an assessment question (a live model builds these)",
    async () => {
      const { body } = await apiCall<NextQuestionResponse>(
        `/v1/sessions/${sacrificial.sessionId}/next`,
        { token, expectStatus: [200, 409, 503] },
      )
      return body
    },
    (value) => value.state === "ready" && value.interactionMode === "assessment",
    { timeoutMs, intervalMs: 3_000 },
  )
}
