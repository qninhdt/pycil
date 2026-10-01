# cross-cutting/auth

Clerk verifies the person. Pycil owns a UUID account. Decisions `H1`–`H14`.

## 1. Two narrow roles

The API is:

1. a **verifier** of Clerk-issued session tokens — it authenticates the person;
2. the **owner of the Pycil account row** — it maps a Clerk subject to a UUID and
   stores nothing else about the session.

```text
Browser
   │  Clerk session token, sent as Authorization: Bearer
   ▼
FastAPI
   │  verify against Clerk JWKS -> subject
   │  subject -> users.clerk_id -> users.id (UUID)
   ▼
route / service authorization on the internal UUID
```

Clerk signs and validates sessions. **Pycil stores no session, no refresh
credential and no token of its own.** There is no local signing path and no
fallback: a Clerk outage fails closed rather than admitting a token this service
minted for itself.

Earlier revisions of this folder described Google OIDC with Pycil-issued HS256
access tokens, rotating refresh sessions and cookies. That design was replaced by
the Clerk decision, and the implemented module is much smaller as a result. The
replaced material is recorded in [../removed.md](../removed.md).

## 2. No BFF

`H1`. The browser calls the API **directly**, sending the Clerk token as a bearer
header. The UI layer proxies nothing and holds no credential of its own.

`apps/web/lib/api/request.ts` reads `window.Clerk.session.getToken()` and sets the
header. That is the whole client half of the integration.

Earlier revisions made same-origin cookies load-bearing here. That is no longer
true and the invariant is withdrawn: there is no cookie, so there is no CSRF
surface to defend and no cross-tab refresh to serialize. Clerk's SDK owns session
lifetime on the client.

## 3. One credential shape

`H2`. Only the `Authorization: Bearer` header is consulted.

```text
1  read Authorization
2  no header            -> unauthenticated
3  scheme is not Bearer -> 401 invalid_authorization
4  empty value          -> 401 invalid_authorization
5  whitespace in value  -> 401 invalid_authorization
6  verify the token
7  resolve the subject to a Pycil UUID
```

The legacy access cookie is deliberately **not** read. Accepting two credential
channels made "which identity is this?" ambiguous, and an ambiguity in identity
resolution is how a bypass is built. Clerk's browser SDK sends the bearer header
itself, so the cookie bought nothing.

Step 5 rejects a second credential smuggled into the same header.

## 4. Verification

`H4`. `pycil/auth/deps.py` verifies:

```text
signature   against Clerk's JWKS, resolved by key id
algorithm   RS256 only, hardcoded — the token's own `alg` is never consulted
issuer      exact, when CLERK_ISSUER is configured
audience    exact, when CLERK_AUDIENCE is configured
expiry      enforced by the verifier
```

The algorithm allow-list is pinned to `["RS256"]`. That is the algorithm-confusion
defence: a token whose header names a symmetric algorithm is not verified against
public key material.

The JWKS client caches keys in memory and refreshes on an unknown key id, so
Clerk's ordinary rotation needs no restart. The cache is bounded (`max_cached_keys=16`,
`lifespan=300`) so a long-lived process cannot accumulate key material without
limit, and its fetch timeout is 5s rather than the 30s default — the client
fetches synchronously with `urllib`, so that call blocks the event loop, and an
unauthenticated caller could otherwise spend 30 seconds of it repeatedly by
sending tokens with unknown key ids.

Every verification failure raises the same stable error code, so a caller cannot
distinguish an expired token from a forged one.

An unconfigured `CLERK_JWKS_URL` is `auth_not_configured`, not an open door.

## 5. Identity is keyed on the Clerk subject

`H7`. `users.clerk_id` is the unique Clerk subject; `users.id` remains the
permanent UUID that every product foreign key points at.

The subject is the **only** lookup key that may create an account. A verified
email may *link* an existing unlinked row, because that is how a pre-cutover
learner keeps their library. It may never create a second account or merge two.

```text
subject found                          -> use it
subject unknown, email matches an
  unlinked row (case-insensitive)      -> claim it, guarded on clerk_id IS NULL
subject unknown, email matches a row
  owned by another subject             -> 409 identity_conflict
subject unknown, email matches nothing -> provision a new account
```

The link is guarded on `clerk_id IS NULL` so two concurrent first sign-ins race to
one winner rather than one overwriting the other's mapping. Email matching is
case-insensitive because the unique index is case-sensitive: a stored
`Learner@Example.com` and a claim of `learner@example.com` are two rows to
Postgres, and matching exactly would orphan the pre-cutover learner's library and
provision a fresh empty account beside it.

Refusing the third case is the only safe answer — linking would hand one learner's
library to another — and it is a conflict the caller resolves rather than a silent
takeover.

The subject→UUID mapping is cached in Redis for 300s and evicted after deletion or
relink.

## 6. Authorization is on the internal UUID

`H5`. A verified subject is an authentication fact, not an authorization one.
Every route checks ownership or readability against the internal UUID
independently of having authenticated: nodes, deck membership, study sessions,
assistant threads and tools, and the credit ledger all authorize on their own.

No email, plan, credit balance or membership is ever carried in a credential. The
account row is read at the point of use.

## 7. Deliberately not built

```text
no local token signing, no refresh sessions, no cookie credential
no token version / revocation list
no CSRF token, no origin-bound session cookie
no vault, no workload identity, no internal mTLS
no per-request token introspection
no proof-of-possession binding
no multi-factor, no local passwords
no dynamic client registration, no implicit flow
```

Each follows from the Clerk decision. Revocation, session lifetime, multi-factor
and password policy are Clerk's to own; reimplementing any of them here would be a
second source of truth for the same question.

## 8. Secrets and configuration

```text
CLERK_JWKS_URL          the API only
CLERK_ISSUER            the API only, optional
CLERK_AUDIENCE          the API only, optional
CLERK_SECRET_KEY        the API only, if any server-side Clerk API call is added
assistant provider key  the API only
content provider keys   the domain worker only
```

The domain worker holds no browser-credential secret, and it cannot mint an
identity. The API holds the assistant provider key because it executes turns
inline.

A **missing required value fails the boot** with every missing name reported at
once. A service that starts and then rejects every request looks healthy while
doing nothing.

## 9. Capabilities that may not be cut

- A hardcoded algorithm allow-list; the token's `alg` is never trusted.
- Issuer and audience validated when configured.
- Every verification failure returns one indistinguishable error code.
- Identity resolves by Clerk subject; an email change keeps one account.
- An email owned by a different subject is a conflict, never a silent link.
- Concurrent first sign-ins produce one account.
- Authorization decisions use the internal UUID, not the Clerk subject.
- A Clerk outage fails closed; there is no local fallback.
- The JWKS cache is bounded and its fetch timeout is short.

## 10. Invariants for the checklist

```text
algorithm allow-list — algorithm confusion rejected
a wrong issuer or audience rejected
an expired token rejected
a forged or malformed token rejected with the same code as an expired one
a second credential in one Authorization header rejected
an unconfigured CLERK_JWKS_URL fails closed, not open
identity resolves by subject; an email change keeps one account
an email owned by another subject returns identity_conflict
two concurrent first sign-ins create exactly one account
every route authorizes on the internal UUID
the worker cannot mint an identity
no credential value appears in an error or a log
```

The older list's cookie, CSRF, refresh-rotation and token-version invariants are
**withdrawn** with the design that needed them.
