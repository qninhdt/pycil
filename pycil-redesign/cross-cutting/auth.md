# cross-cutting/auth

Google OIDC in, a Pycil-signed token out. Decisions `H1`–`H14`.

## 1. Two narrow roles

The API is:

1. an **OIDC client** of Google — it authenticates the person;
2. Pycil's **first-party token issuer** — it signs access tokens and owns refresh
   sessions.

```text
Google
   │  OpenID Connect Authorization Code + PKCE  [R01] [R02]
   ▼
Pycil API
   │  access token + opaque rotating refresh credential
   ▼
Browser (cookies)  ·  mobile (bearer, designed not built)
```

A Google token is **never** used to call a Pycil endpoint. Only a token Pycil
signed is trusted.

This is an auth broker for a fixed set of first-party clients, not an OAuth
platform. Absent by design: dynamic client registration, third-party clients,
consent management, password grant, implicit flow, per-request introspection.

## 2. No BFF

`H1`. The browser calls the API **directly, on the same public origin** routed by
the edge. The UI layer holds no credential and proxies nothing.

Same-origin is load-bearing beyond tidiness:

- the session cookie stays **first-party**;
- assistant SSE and job polling use the same API origin, so cookie and origin
  policy stay uniform on every page;
- there is no server-side token custody to secure, and no forwarding layer that
  can leak one.

Consequences for the UI are in [../modules/web.md](../modules/web.md).

## 3. Login

```text
1  create an OIDC transaction: state, nonce, PKCE S256 challenge, short expiry
2  redirect to Google with scope openid email profile
3  Google returns an authorization code
4  exchange the code for an identity token
5  verify:
     signature against the provider's keys
     algorithm against an allow-list
     exact issuer
     audience
     expiry and issued-at
     exact nonce
     the stored transaction state
     the code is single-use
6  resolve identity by (issuer, subject)
7  create or update the account
8  create a refresh session
9  sign an access token
10 set credentials per client profile
```

The transaction lives in Redis under a **single-use** short-TTL key holding the
verifier, the nonce, and the exact redirect it was minted for. A replayed state
cannot complete a second exchange, and the redirect is validated against an
allow-list so it cannot become an open redirect.

Google's tokens are discarded after login. Pycil calls no Google API on the
learner's behalf, so no Google refresh token is stored.

### Identity is keyed on `(issuer, subject)`

`H7`, and this is a correctness requirement, not a preference. The provider
documents that **email can change** and that the subject is the stable identifier
`[R13]`.

Keying on email means an email change creates a **second account** and abandons
the learner's entire memory state — the one thing in this product that cannot be
regenerated. A separate identity table holds `(issuer, subject) → user`, so a
second provider later is additional rows rather than a schema change.

## 4. One API, two credential shapes

```text
browser   access token in a cookie
mobile    Authorization: Bearer <token>
```

Shared middleware (`H2`):

```text
1  look for the cookie
2  look for the bearer header
3  both present  → reject: ambiguous credentials
4  neither       → unauthenticated
5  verify the token
6  put a normalised principal in the request context
```

Step 3 is not pedantry. Letting precedence pick an identity is how an ambiguity
becomes a bypass: an attacker who can set one of the two chooses which one wins.

Mobile is **designed for, not built**. What must hold from the start so adding it
later is a client registration rather than an architecture change `[R03]`:

- PKCE S256 required, no client secret in an app binary;
- the authorization code single-use, short-lived, bound to the exact client,
  redirect, and challenge;
- the redirect is a claimed HTTPS link, and the flow opens the **system browser**,
  never an embedded web view;
- the access token in memory, the refresh credential in the platform keystore.

## 5. Access token

HS256 (`H3`). Asymmetric signing exists so that a party able to *verify* cannot
*forge*. With exactly one verifier that property buys nothing and costs key
distribution, a public key endpoint, and rotation machinery. One module signs and
verifies, so the algorithm is a one-file change if a second verifier ever appears.

Required claims, all validated (`H4`) `[R05]`, `[R06]`, `[R07]`:

```text
iss   exact issuer
aud   exact audience
typ   token purpose — an access token cannot be replayed where another is expected
sub   the user
exp   expiry
iat   issued-at, rejected if in the future beyond a bounded skew
tv    token version
```

The algorithm allow-list is **hardcoded**; the token's own `alg` is never
consulted. That is the algorithm-confusion attack `[R06]`.

**Not** in the token (`H5`):

```text
email · name · avatar
plan · credit balance
anything that changes while a token lives
```

A token carrying authorization state is stale by construction, and staleness in an
authorization decision is a security bug, not a cache miss. Plan and credit are
read from the account row at the point of use.

Revocation is `tv`, a version integer on the user row, **re-read on every request**
(`H6`). A mismatch rejects. The claim is edge convenience; the row is the truth.

Secret rotation is a preserved capability, not a future upgrade: verification
accepts the previous secret during an overlap window, and removing that would
invalidate live tokens on every rotation.

## 6. Cookies

| | Access | Refresh |
|---|---|---|
| Flags | `HttpOnly`, `Secure` | `HttpOnly`, `Secure` |
| `SameSite` | Lax | Strict or Lax |
| **Path** | `/` | **the refresh endpoint only** (`H12`) |
| Lifetime | short | idle **and** absolute (`H10`) |
| Reachable from JavaScript | never | never |

The narrow refresh path is deliberate: that credential must never reach a resource
route, a log, a delivery stream, or telemetry.

Refresh **rotates cookies and returns no token in the response body.** Nothing in
the browser can read either credential — no local storage, no session storage, no
in-memory custody.

Both idle and absolute expiry, because an absolute limit alone lets an abandoned
session stay valid for its entire lifetime.

### CSRF

Because the browser attaches cookies automatically, every unsafe method requires
(`H11`):

- a CSRF token sent in a request header, bound to the session;
- an **exact** origin check;
- exact-origin CORS — never a wildcard with credentials.

`SameSite` is a defence, **not the boundary**. `HttpOnly` prevents reading a
cookie; it does not make cross-site scripting harmless, because same-origin
JavaScript can still issue authenticated actions. Output encoding, a content
security policy, and server-side authorization all still apply.

The frontend serialises refresh so only one is in flight across tabs. The server
rotates atomically regardless, and both concurrency and replay are tested.

## 7. Refresh sessions

The refresh credential is an **opaque random value**, never a token with claims.
The database stores only a **peppered digest** (`H8`) — the raw value never reaches
persistence.

```text
refresh_sessions
├── id
├── user_id
├── family_id
├── token_digest          peppered, compared in constant time
├── created_at · last_used_at
├── idle_expires_at · absolute_expires_at
└── revoked_at · replaced_by_id
```

Every refresh, in **one transaction under a row lock**:

```text
1  lock the session row
2  digest the presented value
3  compare in constant time
4  check expiry and revocation
5  mint a successor
6  mark the old one replaced, pointing at the successor
7  sign a new access token
8  commit
9  set both cookies
```

A row lock plus one transaction is what makes concurrent attempts serialise rather
than both succeeding.

### Replay

`H9`.

```text
a rotated credential presented again
  ├── inside a bounded grace window, with a live successor
  │     → return the successor
  └── otherwise
        → revoke the entire family
```

The grace window is what makes overlapping tabs and a retry after a crash converge
instead of logging the learner out. The successor is **derivable** from its own
row, so a process that died between committing the rotation and sending the reply
can still be recovered by a retry — but a value whose digest does not match the
persisted successor is never fabricated; that falls through to family revocation.

The window is bounded on both sides and must exceed the refresh-coordination
timeout, or two legitimate concurrent refreshes can be classified as replay.

Redis coordinates overlapping refresh attempts so a single rotation serves them
all, and it stores **no credential** — only which attempt is leading.

## 8. Logout and revocation

```text
logout   revoke the refresh family, clear both cookies, bump the token version
```

Mobile revokes the same session by presenting its refresh credential to a
revocation endpoint `[R09]`; the effect is identical because the family is the
unit of revocation.

Bumping the version is what makes the access token die immediately rather than at
expiry — which matters because there is no per-request denylist.

An open assistant stream observes cancellation or connection loss at its next
yield point. Every later request re-reads `token_version`, so logout needs no
external disconnect call.

Account deletion does the same, then removes data in a hand-ordered sequence — see
[../modules/account.md](../modules/account.md).

## 9. Secrets and configuration

```text
token signing secret        the API only
previous signing secret     the API only, during a rotation overlap
refresh pepper              the API only
Google client secret        the API only
assistant provider key      the API only
content provider keys       the domain worker only
```

The domain worker holds no browser-credential secret. The API holds only the
assistant provider key because it executes Runs inline. That split is enforced
by which service each variable is injected into (`O6`).

A **missing required secret fails the boot** with every missing name reported at
once. A service that starts and then rejects every request looks healthy while
doing nothing.

No vault. On one host with a private network, a boot-time dependency on a secrets
service costs an outage mode and buys rotation that environment injection already
allows.

## 10. Deliberately not built

```text
no vault, no workload identity, no internal mTLS
no per-request token introspection
no proof-of-possession binding
no multi-factor, no local passwords
no dynamic client registration, no implicit flow
no Google token propagation past login
no token carrying authorization state
```

Each because the topology is one application on one host with a private network,
not a multi-tenant cluster.

## 11. Capabilities that may not be cut

Per R4:

- PKCE with a single-use transaction key.
- Nonce and state both verified; the authorization code single-use.
- Identity keyed on `(issuer, subject)`.
- A hardcoded algorithm allow-list.
- Exact issuer, audience, and token purpose validated.
- Token version re-read from the database on every request.
- Refresh stored only as a peppered digest.
- Rotation atomic under a row lock.
- Replay outside the grace window revokes the family.
- Both idle and absolute refresh expiry.
- Cookie flags, the narrow refresh path, CSRF plus an origin check.
- Cookie and bearer together rejected.
- Signing-secret rotation with an overlap.

## 12. Invariants for the checklist

```text
algorithm allow-list — algorithm confusion rejected
exact issuer and audience; a wrong audience rejected
a token with the wrong purpose rejected
expired token rejected; clock skew bounded
a bumped token version rejects an unexpired token
the identity token: signature, nonce, state, single-use code
a replayed OIDC state cannot complete a second exchange
a redirect outside the allow-list rejected
identity resolves by (issuer, subject); an email change keeps one account
refresh rotation is atomic under concurrency
a rotated credential inside the grace window returns its successor
a rotated credential outside the window revokes the family
an expired-by-idle session is rejected while still inside its absolute window
cookie flags: HttpOnly, Secure, SameSite; refresh scoped to its endpoint
an unsafe method without a CSRF token rejected
an unsafe method from a foreign origin rejected
cookie + bearer together → rejected as ambiguous
the refresh credential never appears in a response body
logout revokes the family and invalidates subsequent API and SSE requests
a missing required secret fails the boot, naming every missing variable
```
