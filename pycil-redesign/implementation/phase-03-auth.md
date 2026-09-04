---
phase: 3
title: "Auth"
status: pending
priority: P1
effort: "3-4d"
dependencies: [1]
---

# Phase 3: Auth

## Overview

Move browser credentials into cookies the API owns, key identity on the provider's
stable subject, and add the three token claims and the CSRF boundary that cookie
auth requires. The BFF is already gone from phase 1, so this is what replaces it.

## Requirements

**Functional**

- Access token in an `HttpOnly` `Secure` cookie; refresh in a second cookie scoped
  to the refresh endpoint only (`H12`).
- Bearer accepted for a non-browser client; **both present is rejected** (`H2`).
- Claims validated: algorithm allow-list, `iss`, `aud`, `typ`, `sub`, `exp`, `iat`
  with bounded skew (`H4`).
- Identity keyed on `(issuer, subject)` in a dedicated table (`H7`).
- Idle **and** absolute refresh expiry (`H10`).
- CSRF token plus an exact origin check on every unsafe method (`H11`).
- Errors as RFC 9457 Problem Details (`H14`).
- Logout revokes the family, bumps the token version, and calls the realtime
  disconnect — logged when it fails.

**Non-functional**

- Nothing mutable in the token (`H5`): no email, no plan, no balance.
- HS256 retained (`H3`); the signing module stays the only place that signs or
  verifies.
- Signing-secret rotation with an overlap window preserved.

## Architecture

```text
browser                              mobile (designed, not built)
  Cookie: access  (HttpOnly, path /)   Authorization: Bearer
  Cookie: refresh (HttpOnly, path /v1/auth/refresh)
        │                                  │
        └────────────┬─────────────────────┘
                     ▼
              one middleware
                1 look for the cookie
                2 look for the bearer header
                3 both  → reject, ambiguous
                4 neither → unauthenticated
                5 verify: alg allow-list, iss, aud, typ, sub, exp, iat
                6 re-read the token version from the row
                7 normalised principal in the request context
```

**Why rejecting both is not pedantry.** Letting precedence pick an identity is how
an ambiguity becomes a bypass: an attacker who can set one of the two chooses which
one wins.

**Why `(issuer, subject)`.** The provider documents that email changes and that the
subject is stable. Keying on email means an email change creates a second account
and abandons the learner's memory state — the one asset in this product that cannot
be regenerated.

**Refresh replay, unchanged in shape and kept:**

```text
a rotated credential presented again
  ├── inside the grace window, with a live successor → return the successor
  └── otherwise                                      → revoke the family
```

The grace window is what makes overlapping tabs and a retry-after-crash converge
instead of logging the learner out. It must exceed the coordination timeout, or two
legitimate concurrent refreshes are classified as replay.

## Related Code Files

**Create**

- `apps/api/pycil/auth/cookies.py` — set, clear, and the flag policy
- `apps/api/pycil/auth/csrf.py` — token issue and verify, plus the origin check
- `apps/api/pycil/common/problem.py` — RFC 9457 envelope
- migration: `external_identities` — already in the phase-1 baseline; this phase
  backfills nothing because there is no data

**Modify**

- `apps/api/pycil/auth/tokens.py` — add `iss`, `aud`, `typ` to signing and to the
  required set
- `apps/api/pycil/auth/deps.py` — the middleware above, replacing bearer-only
- `apps/api/pycil/auth/router.py` — the callback and refresh set cookies and return
  **no token in the body**
- `apps/api/pycil/auth/oauth.py` — resolve by `(issuer, subject)`
- `apps/api/pycil/auth/refresh_sessions.py` — add idle expiry beside absolute
- `apps/api/pycil/common/errors.py` — emit Problem Details
- `apps/api/pycil/main.py` — CORS exact-origin with credentials

**Flatten** (`A2`) — `auth` is already flat and is the model the other modules
follow.

## Implementation Steps

1. Add `iss`, `aud`, `typ` to signing and to the required-claims set. Reject a token
   whose purpose does not match the endpoint.
2. Write `cookies.py` with the flag policy and the two paths.
3. Rewrite the callback: set both cookies, return no credential in the body.
4. Rewrite refresh: rotate under the row lock as today, then **replace both
   cookies**, still returning nothing in the body.
5. Rewrite `deps.py` as the middleware above, including the both-present rejection.
6. Add `external_identities` resolution to the OAuth path; email becomes an observed
   field.
7. Add idle expiry to the session row and to every expiry check.
8. Write `csrf.py`: issue on session establishment, verify on unsafe methods
   alongside an exact origin check.
9. Convert the error envelope to Problem Details, keeping the domain code as an
   extension member.
10. Wire the realtime disconnect into logout and log its failure — it is the only
    signal that a socket outlived a revocation.

## Todo

- [ ] `iss` / `aud` / `typ` signed and required
- [ ] `cookies.py` with per-credential paths
- [ ] Callback sets cookies, body carries no credential
- [ ] Refresh replaces cookies, body carries no credential
- [ ] Middleware: cookie, bearer, both → reject
- [ ] `external_identities` keyed on `(issuer, subject)`
- [ ] Idle expiry beside absolute
- [ ] CSRF token plus exact origin check
- [ ] Problem Details envelope
- [ ] Logout: revoke, bump, disconnect, log on failure
- [ ] `auth.md` §12 covered by named tests

## Success Criteria

- [ ] Algorithm confusion rejected
- [ ] Wrong audience, wrong issuer, wrong purpose each rejected
- [ ] A bumped token version rejects an unexpired token
- [ ] An email change keeps one account and one memory state
- [ ] Two providers with the same subject are two identities
- [ ] Rotation atomic under concurrency
- [ ] A rotated credential inside the window returns its successor
- [ ] A rotated credential outside the window revokes the family
- [ ] A session idle past its window is rejected while inside its absolute window
- [ ] Cookie and bearer together → rejected
- [ ] An unsafe method without a CSRF token, or from a foreign origin → rejected
- [ ] No credential in any response body
- [ ] Every error response is `application/problem+json`
- [ ] `auth.md` §12 fully covered by named tests

## Risk Assessment

**CSRF is new code on the authentication path.** Signal: a legitimate unsafe request
is rejected, or worse, a foreign-origin one is accepted. Response: the origin check
is the coarse control and the token is the fine one; both must be present before
cookie auth is considered done, because `SameSite` alone is explicitly not the
boundary.

**The grace window interacts with the coordination timeout.** If the window is
shorter, two legitimate concurrent refreshes look like replay and revoke the family
— a logout for a learner who did nothing wrong. Signal: unexplained forced
re-authentication under multi-tab use. Response: assert the relationship at boot
rather than documenting it.

**Nothing can authenticate between phase 1 and this phase.** Signal: none — it is
expected. Response: the golden journey does not run until phase 11.

**Bearer remains for a client that does not exist yet.** Keeping it costs one branch
and keeps the mobile path a client registration rather than an architecture change.
The risk is the reverse: removing it now and discovering the cookie path has assumed
a browser everywhere.
