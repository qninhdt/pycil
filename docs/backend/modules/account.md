# Account, identity, preferences, and usage

## Responsibility

The account module maps a verified Clerk subject to a Pycil user, provisions a Library,
resolves saved preferences, checks plan features, and accounts for assistant usage.
It does not implement checkout, payment webhooks, a public plan-change route, or a
separate local-password login system.

## Current API

| Operation | Auth | Purpose |
| --- | --- | --- |
| `GET /v1/me` | Required | Private profile, resolved/effective preferences, three root IDs |
| `PATCH /v1/me/settings` | Required | Merge supported saved preferences and return profile |
| `PATCH /v1/me/profile` | Required | Edit display name, handle and bio |
| `GET /v1/me/usage` | Required | Current anchored period and remaining units |
| `GET /v1/users/{user_id}` | Optional | Public identity, handle/bio/joined date and Published root |
| `GET /v1/users:lookup?handle={handle}` | Optional | Same safe profile by current canonical handle |

The private profile exposes `id`, `display_name`, `plan`, `settings`,
`effective_learning`, `learning_restriction`, safe `learning_options`, handle/bio/joined
date, and Library/Personal/Published IDs. Profile reads refresh persisted values.
It does not expose the Clerk subject. Public profiles omit settings, plan, learning,
usage and private root IDs, even when the requester is authenticated.

## Identity flow

1. Reject absent or malformed private-route authorization.
2. Verify the signed JWT against configured JWKS/issuer and optional audience.
3. Look up a bounded detached context under `actor:v3:<subject>`.
4. On a miss, look up the user by subject. If missing, check that the Clerk user exists
   before provisioning, preventing a stale signed identity from recreating a deleted account.
5. Initialize absent display name from Clerk first/last name and generate a unique handle
   from that name. A nameless Clerk profile uses `Pycil learner`. Existing names/handles
   are preserved, including owner edits. Upsert with conflict handling and provision
   all three roots in the same transaction; retry handle collisions inside a savepoint.
6. Build a frozen actor context including display name/handle and optionally cache it
   for 60 seconds. A cache hit needs no SQL or Clerk profile request. Expiry, invalidation
   or Redis failure falls back to SQL; a complete identity does not call Clerk again.

Cache hits do not skip JWT verification. They do not necessarily call Clerk or refresh
every account field on every request. Writes requiring account existence check the user
again; plan-sensitive operations explicitly fetch current plan/allowance rather than
treating a detached cached plan as entitlement authority.

Existing accounts are expected to have roots from migration. Auth is not a general
repair-on-read service for corrupt or incomplete roots.

## Saved versus effective preferences

`users.settings` is a sparse JSON object. Missing known values resolve against current
product defaults. The settings response distinguishes stored intent from a learning
selection that is currently feasible under the user's plan.

Complete PATCH example under the **current** contract:

```json
{
  "locale": "en",
  "timezone": "Asia/Ho_Chi_Minh",
  "translation_language": "vi",
  "assistant": {
    "auto_approve": false
  },
  "learning": {
    "questions_per_sense": 2,
    "max_sense_count": 10
  }
}
```

Only supplied fields are merged. Nested learning and assistant fields merge with saved
preferences; unrelated settings are not discarded. Explicit null and unknown keys
are rejected. Types/formats must be legal native values and allowed by product policy.

`assistant.auto_approve` is a strict Boolean, default false from account YAML defaults.
The Assistant panel owns its toggle; the Settings page shows only General and Learning.
The value persists per account through the same PATCH endpoint.

Users without ADVANCED_GRADING cannot newly request typed formats. Free preparation effectively uses SINGLE_CHOICE while preserving saved typed preferences. Pro filters unsupported type/format pairs; if no supported pair remains, it returns
`infeasible_learning_preferences`. `/me` instead reports `effective_learning=null`
and a restriction so the client can render settings and explain the issue.

Stored paid preferences are preserved across downgrade. Settings writes refresh the
user inside a transaction, then invalidate the actor cache after commit. There is no
settings revision or conflict-aware draft merge beyond the explicit PATCH semantics.

Maximum senses times questions per sense must not exceed `max_questions_per_prepare=60`.
Old budget fields are rejected. Handle trims/lowercases ASCII, matches
`[a-z][a-z0-9_]{2,29}`, and has database uniqueness. It is generated on first identity initialization and cannot
be explicitly cleared. Bio trims to at most 500 characters; null clears it. Omission
preserves either field. Concurrent duplicate handles return `handle_unavailable` (409).
Renames invalidate the old handle URL; UUID identity remains stable. Display names
trim whitespace and require 1–255 characters; explicit null/empty values are rejected.
All three profile fields are owner-editable; omission preserves existing values.
Display-name edits do not regenerate the handle or update Clerk. Profile writes
invalidate the actor cache after commit. No country, avatar upload, email-derived handle
or recurring Clerk profile sync is added. Existing missing identity initializes once
on the next authenticated cache miss; migration does not contact Clerk.

## Anchored usage periods

Periods derive from `cycle_anchor` in UTC. A month boundary retains the anchor's time
and clips the day to that month's length. An anchor on the 31st therefore has a shorter
day number in February rather than skipping the period. Reporting is not a calendar-month reset.

Reading usage is read-only: absent period means zero consumption with the current plan
allowance. For an existing period, allowance is the maximum of stored allowance and
current plan allowance. Remaining units are clamped to zero, not negative.

Admission checks current user/plan, feature availability, and remaining allowance.
It does not reserve predicted usage. Concurrent already-admitted turns can finish with
usage above allowance; future admissions are then denied. Do not document a hard
reservation system that is not implemented.

Settlement uses a unique execution key, a short event-key lock and user usage lock,
creates a period only when needed, and adds reported integer units exactly once.
Conflicting repeated settlement returns `usage_event_conflict`. Unknown token reports
are represented through unmetered-call bookkeeping rather than invented costs.

The internal `change_plan()` service preserves usage and does not lower an already
granted period allowance. It invalidates the actor cache. There is no public route
exposing that helper or an automatic billing integration in this source.

## Failure behavior

- Missing Clerk identity: 401 `invalid_credentials`.
- Clerk lookup transport/non-success failure: 503 `identity_service_unavailable`.
- Missing current account: 404 `account_not_found`.
- Unsupported feature or exhausted allowance: 403 `feature_not_available` / `allowance_exhausted`.
- Invalid saved selection: 422 `invalid_preferences`; impossible effective learning:
  `infeasible_learning_preferences`.
- Optional actor cache failure falls back to database reads, not to accepting an invalid token.

## Sources and tests

- [Router](../../../apps/api/pycil/account/api.py), [auth](../../../apps/api/pycil/account/auth.py), [schemas](../../../apps/api/pycil/account/schemas.py)
- [Usage](../../../apps/api/pycil/account/usage.py), [lifecycle](../../../apps/api/pycil/account/lifecycle.py)
- [Account integration](../../../apps/api/tests/integration/test_account_lifecycle.py), [preferences HTTP tests](../../../apps/api/tests/system/test_preferences_api.py), [identity unit tests](../../../apps/api/tests/unit/test_identity.py)
