import { readFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

/**
 * The repository-root `.env`, read directly.
 *
 * The suite has to seal a cookie the running web container will accept, which
 * means using *its* `SESSION_PASSWORD` and `SESSION_COOKIE_NAME` rather than a
 * copy. Both live in the root `.env` that `docker compose` interpolates from, so
 * reading that file is what keeps the two in lockstep: a rotated password breaks
 * the suite loudly instead of producing a cookie the app silently discards as
 * unsealable, which would surface as "every spec redirects to /login".
 *
 * Parsed here rather than with `dotenv` because the need is four keys and one
 * file, and because `dotenv` would also mutate `process.env` for the whole
 * worker, quietly overriding values a caller set on the command line.
 */

const here = path.dirname(fileURLToPath(import.meta.url))
/** `apps/web/tests/e2e/fixtures` -> repository root. */
export const repoRoot = path.resolve(here, "../../../../..")
const envPath = path.join(repoRoot, ".env")

/**
 * The two files global setup writes and the workers read.
 *
 * Both live under `tests/e2e/.auth/`, which is git-ignored: the sealed cookie is
 * a live credential for the seeded identity, and the fixture names rows in
 * whatever database the run pointed at. Neither is a review artifact.
 *
 * They are constants rather than literals repeated in two files because the
 * handoff only works if the writer and the reader agree, and a typo in one of
 * two string literals fails as "global setup must run first" on a run where it
 * did.
 */
const authDir = path.join(here, "..", ".auth")
/** The Playwright `storageState` holding the sealed session cookie. */
export const AUTH_STATE_PATH = path.join(authDir, "state.json")
/** The seeded library structure and content the specs assert against. */
export const FIXTURE_PATH = path.join(authDir, "fixture.json")

function parseEnvFile(contents: string): Record<string, string> {
  const values: Record<string, string> = {}
  for (const rawLine of contents.split("\n")) {
    const line = rawLine.trim()
    if (!line || line.startsWith("#")) continue
    const separator = line.indexOf("=")
    if (separator === -1) continue
    const key = line.slice(0, separator).trim()
    let value = line.slice(separator + 1).trim()
    // Compose keeps the quotes out of the value, so strip a matched pair. An
    // unmatched quote is left alone rather than half-removed.
    if (
      (value.startsWith('"') && value.endsWith('"') && value.length >= 2) ||
      (value.startsWith("'") && value.endsWith("'") && value.length >= 2)
    ) {
      value = value.slice(1, -1)
    }
    // Last write wins, matching how compose and pydantic-settings resolve a key
    // that appears twice in one file.
    values[key] = value
  }
  return values
}

let cached: Record<string, string> | null = null

export function envFile(): Record<string, string> {
  if (cached) return cached
  try {
    cached = parseEnvFile(readFileSync(envPath, "utf8"))
  } catch (error) {
    throw new Error(
      `Could not read ${envPath}, which holds SESSION_PASSWORD and SESSION_COOKIE_NAME. ` +
        "The E2E suite seals a cookie with the same values the web container runs " +
        `with, so it cannot proceed without them. Underlying error: ${String(error)}`,
    )
  }
  return cached
}

/**
 * An explicit process variable wins over the file, so a one-off run can point at
 * a different stack without editing `.env`.
 */
export function envValue(key: string, fallback?: string): string {
  const value = process.env[key] ?? envFile()[key] ?? fallback
  if (value === undefined) {
    throw new Error(
      `${key} is set neither in the environment nor in ${envPath}. ` +
        "See .env.example for what it should hold.",
    )
  }
  return value
}

/**
 * The cookie name the app reads. Kept as one helper because two places need it
 * to agree: the cookie this suite writes, and the cookie the app looks for.
 * `session.ts` defaults to `pycil_session`, so the default is repeated here
 * rather than assumed to be set.
 */
export function sessionCookieName(): string {
  return envValue("SESSION_COOKIE_NAME", "pycil_session")
}

export function sessionPassword(): string {
  const password = envValue("SESSION_PASSWORD")
  if (password.length < 32) {
    throw new Error(
      `SESSION_PASSWORD is ${password.length} characters; the app refuses to boot ` +
        "under 32, so a shorter value means the stack under test is not running " +
        "the app this suite is written against.",
    )
  }
  return password
}

/** The single browser origin: app, `/v1`, and SSE all arrive here. */
export function baseUrl(): string {
  return process.env.E2E_BASE_URL || "https://localhost"
}

/**
 * The API as reached from the host, bypassing Caddy.
 *
 * Seeding talks to this rather than to the public origin. The reason is TLS
 * rather than routing: Caddy serves a certificate from its own local CA, and
 * Node's `fetch` has no per-request escape hatch equivalent to Playwright's
 * `ignoreHTTPSErrors`. The browser specs still go through the public origin,
 * which is what the single-origin requirement is about; only the fixture setup
 * takes the loopback port.
 */
export function apiBaseUrl(): string {
  if (process.env.E2E_API_URL) return process.env.E2E_API_URL
  // `API_HOST_PORT` is a compose bind spec such as `127.0.0.1:8000`, which is
  // already `host:port` — but it may also be a bare port.
  const bind = envValue("API_HOST_PORT", "127.0.0.1:8000")
  return bind.includes(":") ? `http://${bind}` : `http://127.0.0.1:${bind}`
}

/** The compose service and CLI used for the auth seam. */
export const composeApiService = "api"

/**
 * The compose service holding the per-user quota counters.
 *
 * Named here rather than at the call site so the one place that reaches into Redis
 * is as explicit about which container it means as the API seam above is.
 */
export const composeRedisService = "redis"

/**
 * The Redis password, matching the compose default.
 *
 * `docker-compose.yml` starts the server with `--requirepass`, so an unauthenticated
 * `redis-cli` inside the container is refused. The default is repeated here for the
 * same reason as the session cookie name: the stack runs on it unless `.env` says
 * otherwise, and assuming it is set would fail with a confusing NOAUTH rather than a
 * clear message.
 */
export function redisPassword(): string {
  return envValue("REDIS_PASSWORD", "redis-dev-only")
}

/**
 * A fresh identity per run, and that is a correctness requirement rather than
 * hygiene.
 *
 * Three things this suite exercises are per-user budgets that do not reset
 * between runs:
 *
 * - **Scheduling state.** A sense the previous run answered is terminal for the
 *   rest of the day, so a re-run on the same account admits nothing and every
 *   study spec would fail with "admitted nothing" — a stale-state artefact that
 *   looks exactly like a planner bug.
 * - **The grading quota**, a per-user Redis budget the quota spec deliberately
 *   drains.
 * - **The generation slot budget**, also per user.
 *
 * A per-run address makes runs idempotent without any teardown. It costs almost
 * nothing, because the expensive artefacts are *not* per user: generated words
 * and prepared questions live in Lexi's own store, keyed by sense and level, so
 * a new identity still inherits warm supply from every previous run. The first
 * run pays the model; later runs do not.
 *
 * Pin it with `E2E_IDENTITY_EMAIL` to reuse one account deliberately — useful
 * when inspecting what a failing run actually left behind.
 */
let runIdentityEmail: string | null = null

export function devIdentityEmail(): string {
  if (process.env.E2E_IDENTITY_EMAIL) return process.env.E2E_IDENTITY_EMAIL
  // Memoised, and that is load-bearing. Deriving the address from the clock on
  // every call returns a *different* address each time, so the reporter would
  // name one identity, the CLI would seed a second, and the sealed cookie would
  // belong to whichever call happened last — leaving the specs authenticated as
  // an account the fixture never seeded anything into.
  if (!runIdentityEmail) {
    runIdentityEmail = `e2e+${runStamp()}@pycil.local`
  }
  return runIdentityEmail
}

/**
 * A learner of this run's own, isolated from every other spec.
 *
 * Scheduling state is keyed `(user_id, sense_id)` (`learning/models.py`), so the
 * first spec to study the fixture deck schedules every sense for a later day and
 * leaves the next spec on "Nothing due right now". Sharing one learner across
 * specs therefore makes them order-dependent: whichever runs first passes.
 *
 * A fresh learner is the right isolation boundary rather than a fresh deck,
 * because prepared question supply is keyed by word and level and explicitly
 * *not* by user (`jobs/generate_question.py` drops `owner_uid` with that note).
 * A new learner sees the same senses as new again and reuses the supply the run
 * already warmed, so isolation costs a CLI call rather than another round of
 * model generation.
 *
 * `slug` names the spec, so a failure points at the learner that produced it.
 */
export function specIdentityEmail(slug: string): string {
  const safe = slug.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")
  return `e2e+${runStamp()}-${safe}@pycil.local`
}

/**
 * One stamp per process, shared by the run-wide and per-spec identities.
 *
 * Memoised for the same reason `devIdentityEmail` is: a stamp read from the clock
 * on each call produces a different address every time it is asked for.
 */
let stamp: string | null = null

function runStamp(): string {
  if (!stamp) stamp = Date.now().toString(36)
  return stamp
}

export interface E2EEnv {
  /** The single public origin the browser uses. */
  baseURL: string
  /** The loopback API bind the fixture seeds through. */
  apiURL: string
  identityEmail: string
  cookieName: string
}

/**
 * Resolves every value the run depends on, once, before anything is seeded.
 *
 * Eager rather than lazy on purpose: `sessionPassword()` throws when the value is
 * missing or too short, and the useful moment for that failure is the first line
 * of setup — not thirty seconds later, after generation has run, when a browser
 * finally presents a cookie the app cannot unseal.
 */
export function loadE2EEnv(): E2EEnv {
  sessionPassword()
  return {
    baseURL: baseUrl(),
    apiURL: apiBaseUrl(),
    identityEmail: devIdentityEmail(),
    cookieName: sessionCookieName(),
  }
}
