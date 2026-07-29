import { execFile } from "node:child_process"
import { readdir } from "node:fs/promises"
import type { Dirent } from "node:fs"
import path from "node:path"
import { promisify } from "node:util"

import { sealData } from "iron-session"

import {
  apiBaseUrl,
  composeApiService,
  devIdentityEmail,
  repoRoot,
  sessionCookieName,
  sessionPassword,
} from "./env"

const run = promisify(execFile)

/**
 * The E2E authentication seam.
 *
 * There is no login route to drive. Sign-in is Google OAuth end to end
 * (`apps/api/pycil/auth/oauth.py` hardcodes Google's real endpoints), so a
 * browser cannot complete it unattended and there is no local IdP to swap in.
 *
 * What exists instead is `apps/api/pycil/auth/dev_identity.py`: an argparse entry
 * point, mounted on no router, that seeds one local identity and prints a *normal*
 * Pycil bearer token — the same `tokens.sign_access` output the OAuth callback
 * would hand back. This module runs that CLI as a compose one-shot, reads the
 * token, and seals it into a cookie with the app's own `sessionOptions`.
 *
 * Two things are deliberately NOT done here.
 *
 * **No dev-login route is added.** A route reachable over HTTP is a route an
 * attacker can reach, and gating it on `NODE_ENV` alone has shipped to production
 * often enough to be a genre. `assertNoDevAuthRoute` below fails the suite if one
 * ever appears.
 *
 * **`getSession` is not stubbed.** The sealing *is* the thing under test: the
 * cookie produced here is unsealed by the real `lib/auth/session.ts` in the real
 * container, so a wrong password, a mismatched cookie name, or a drifted
 * `SessionData` shape fails a spec instead of passing a mock. That is why this
 * calls `sealData` from `iron-session` rather than writing its own envelope.
 */

export interface DevIdentity {
  email: string
  accessToken: string
  expiresIn: number
}

/**
 * The viewer as `/v1/me` reports it.
 *
 * Both nullable fields are collapsed from "absent" to `null` at the read, exactly
 * as `app/api/auth/callback/route.ts` does when it seals a real OAuth session, so
 * the cookie this suite writes and the cookie a real sign-in writes have the same
 * shape rather than differing by an `undefined`.
 */
export interface Viewer {
  id: string
  email: string
  name: string | null
  image: string | null
}

/**
 * The session shape `lib/auth/types.ts` declares.
 *
 * Restated here rather than imported because this file runs in Node under
 * Playwright, and `lib/auth/session.ts` — the module that would come with it —
 * is `server-only` and validates `SESSION_PASSWORD` at import time. The fields
 * are asserted against the running app by every spec that renders a viewer, so
 * drift surfaces as a failure rather than as a silently ignored key.
 */
interface SessionData {
  accessToken?: string
  refreshToken?: string
  expiresAt?: number
  refreshExpiresAt?: number
  user?: {
    id: string
    email: string
    name: string | null
    image: string | null
  }
  isLoggedIn: boolean
}

/** Parses the CLI's `key=value` lines. */
function parseCliOutput(stdout: string): DevIdentity {
  const values: Record<string, string> = {}
  for (const line of stdout.split("\n")) {
    const separator = line.indexOf("=")
    if (separator === -1) continue
    values[line.slice(0, separator).trim()] = line.slice(separator + 1).trim()
  }
  const { email, access_token: accessToken, expires_in: expiresIn } = values
  if (!email || !accessToken) {
    throw new Error(
      "The dev_identity CLI printed no token. Expected `email=`, `access_token=` " +
        `and \`expires_in=\` lines, got:\n${stdout}`,
    )
  }
  return { email, accessToken, expiresIn: Number(expiresIn) || 0 }
}

/**
 * Runs the identity CLI inside the API container.
 *
 * `exec`, not `run`: the API service is already up and healthy by the time the
 * suite starts, and a `run` would start a second container with its own
 * connection to Postgres for no benefit. The CLI is idempotent — it reuses the
 * identity if the email already exists — so repeated runs are safe.
 *
 * The CLI itself calls `assert_dev_identity_allowed`, which refuses when
 * `ENVIRONMENT` is production or `DEV_IDENTITY_ENABLED` is false. That refusal is
 * the desired behaviour, so it is surfaced with the remedy rather than caught.
 */
export async function mintDevIdentity(
  /**
   * Which identity to seed. Defaults to the run-wide one.
   *
   * Passing an explicit address is what lets each spec own its own learner. FSRS
   * scheduling state is keyed `(user_id, sense_id)` (`learning/models.py`), so two
   * specs sharing an identity share one pool of due work: the first to run a
   * session schedules every sense into the future and the rest find the deck
   * empty. A per-spec address is a clean slate at no cost, because prepared
   * question supply is keyed per word rather than per user
   * (`jobs/generate_question.py`) and is therefore still shared.
   */
  email: string = devIdentityEmail(),
): Promise<DevIdentity> {
  try {
    const { stdout } = await run(
      "docker",
      [
        "compose",
        "exec",
        "-T",
        composeApiService,
        "python",
        "-m",
        "pycil.auth.dev_identity",
        "--email",
        email,
      ],
      { cwd: repoRoot, maxBuffer: 1024 * 1024 },
    )
    return parseCliOutput(stdout)
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    throw new Error(
      "Could not mint a development identity through the API container.\n\n" +
        "This is the E2E auth seam: the CLI is the only way in, because sign-in is " +
        "Google OAuth and there is deliberately no dev-login route.\n\n" +
        "Check that the stack is up (`docker compose ps`) and that " +
        "DEV_IDENTITY_ENABLED=true with ENVIRONMENT unset or development.\n\n" +
        detail,
    )
  }
}

/**
 * Reads the viewer the API will report for this token.
 *
 * The CLI prints an email but not an id, and the session carries the id the app
 * renders and scopes by. Rather than decode the JWT's `sub` — which would mean
 * this suite reimplementing a claim contract it does not own — the token is spent
 * on `/v1/me`, exactly as `app/api/auth/callback/route.ts` does after an OAuth
 * exchange. That also proves the token works before any browser opens, so a bad
 * token fails setup with a clear message instead of every spec redirecting to
 * `/login`.
 */
export async function readViewer(accessToken: string): Promise<Viewer> {
  const response = await fetch(`${apiBaseUrl()}/v1/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  })
  if (!response.ok) {
    throw new Error(
      `The API rejected the minted token at /v1/me with ${response.status}. ` +
        "The token and the API must be signed with the same AUTH_JWT_SECRET; a " +
        "mismatch here means the CLI ran against a different configuration than " +
        "the running API.",
    )
  }
  const viewer = (await response.json()) as {
    id: string
    email: string
    name?: string | null
    image?: string | null
  }
  return {
    id: viewer.id,
    email: viewer.email,
    name: viewer.name ?? null,
    image: viewer.image ?? null,
  }
}

/**
 * Seals a session cookie the running app will accept.
 *
 * `sealData` is `iron-session`'s own primitive, the one `getIronSession` uses, so
 * the envelope, the key derivation, and the TTL handling are the library's rather
 * than this file's. `ttl` matches the token's own lifetime: a cookie outliving its
 * bearer token would leave the suite signed in with a token the API refuses,
 * which reads as a puzzling 401 rather than as an expiry.
 *
 * No `refreshToken` is set, because the CLI issues none. That is fine and
 * deliberate: `lib/api/request.ts` only attempts a refresh when one is present,
 * and the access token's TTL is a week.
 */
export async function sealSessionCookie(
  identity: DevIdentity,
  /** Already read by the caller; passing it in avoids a second `/v1/me`. */
  viewer: Viewer,
): Promise<string> {
  const nowInSeconds = Math.floor(Date.now() / 1000)

  const session: SessionData = {
    accessToken: identity.accessToken,
    expiresAt: nowInSeconds + identity.expiresIn,
    user: viewer,
    isLoggedIn: true,
  }

  return sealData(session, {
    password: sessionPassword(),
    ttl: identity.expiresIn,
  })
}

/**
 * Fails the run if a development authentication route ever appears.
 *
 * This is the guard that keeps the seam above honest. The temptation, whenever
 * E2E authentication is awkward, is to add `POST /api/auth/dev-login` "just for
 * tests" — and gating it on `NODE_ENV !== "production"` has shipped to
 * production often enough to be a genre of incident. Since the CLI seam removes
 * the need entirely, the absence is asserted mechanically rather than trusted to
 * review.
 *
 * The check is on the source tree rather than on a live request, because a route
 * that exists but 404s on a probe (behind an env flag that happens to be off in
 * this environment) is exactly the thing that must not ship.
 */
export async function assertNoDevAuthRoute(): Promise<void> {
  const appDir = path.join(repoRoot, "apps", "web", "app")
  const offenders: string[] = []

  async function walk(dir: string): Promise<void> {
    let entries: Dirent[]
    try {
      entries = await readdir(dir, { withFileTypes: true })
    } catch {
      return
    }
    for (const entry of entries) {
      const full = path.join(dir, entry.name)
      if (entry.isDirectory()) {
        if (/dev-login|dev-token|dev-auth|dev_identity/i.test(entry.name)) {
          offenders.push(path.relative(repoRoot, full))
        }
        await walk(full)
      }
    }
  }

  await walk(appDir)

  if (offenders.length > 0) {
    throw new Error(
      "A development authentication route exists in the web app:\n\n" +
        offenders.map((file) => `  - ${file}`).join("\n") +
        "\n\nThis suite authenticates through the dev_identity CLI precisely so no " +
        "such route is needed. If one is genuinely unavoidable it must be gated on " +
        'both `NODE_ENV !== "production"` AND an explicit E2E_AUTH_ENABLED flag, ' +
        "and this assertion updated deliberately rather than deleted.",
    )
  }
}

/** Everything a run needs from the identity seam, resolved once. */
export interface MintedSession {
  user: Viewer
  accessToken: string
  storageState: Awaited<ReturnType<typeof buildStorageState>>
}

/**
 * Mints an identity and seals it into a browser-ready cookie.
 *
 * The access token is returned alongside the cookie because the fixture seeds
 * through the API directly — creating folders, decks and senses over HTTP is far
 * more robust than driving the same setup through the UI, and it keeps a failure
 * in seeding distinguishable from a failure in the screen under test.
 */
export async function mintSessionState(
  /** Which learner to mint. Omit for the run-wide identity used by global setup. */
  email?: string,
): Promise<MintedSession> {
  const identity = await mintDevIdentity(email)
  // Spent once, here: the viewer is needed both inside the sealed cookie and by
  // the specs that assert on the signed-in identity.
  const viewer = await readViewer(identity.accessToken)
  const storageState = await buildStorageState(identity, viewer)
  return { user: viewer, accessToken: identity.accessToken, storageState }
}

/** The cookie in Playwright's `storageState` form. */
export async function buildStorageState(identity: DevIdentity, viewer: Viewer) {
  const sealed = await sealSessionCookie(identity, viewer)
  return {
    cookies: [
      {
        name: sessionCookieName(),
        value: sealed,
        // Host-only, matching what `getIronSession` writes: no leading dot, so it
        // is not offered to sibling hosts.
        domain: "localhost",
        path: "/",
        // Playwright wants seconds since the epoch; -1 would make it a session
        // cookie and lose it on context close.
        expires: Math.floor(Date.now() / 1000) + identity.expiresIn,
        httpOnly: true,
        // The app sets `secure` everywhere except an explicitly declared local
        // development run, and the stack under test serves HTTPS through Caddy.
        secure: true,
        sameSite: "Lax" as const,
      },
    ],
    origins: [],
  }
}
