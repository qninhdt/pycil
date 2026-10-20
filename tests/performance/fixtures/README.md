# Private performance fixtures

Keep actual JSON/token files outside Git (for example in an ignored course lab
directory or `~/.local/share/pycil/performance`), mode `0600`. No example bearer
tokens or production exports belong here.

The JSON contract is checked by [contract.js](../contract.js):

| Field | Meaning |
| --- | --- |
| `dataset_hash` | SHA-256 of the canonical, sorted non-secret dataset manifest; exclude tokens/expiry so renewing credentials preserves dataset identity |
| `word_ids` | 1–100 unique positive IDs of existing generated words, state `done`, with senses |
| `users` | Dedicated real Clerk identities, each with `account_id`, owned `node_id`, expected positive `total` senses, signed `token` and ISO `expires_at` |
| `search_queries` | Nonempty representative exact/prefix/reference queries whose results exist |

Create the identity through Clerk's normal supported administrative flow and
sign in before measurement. Provision its private deck through the real API with
existing senses; do not generate paid content to populate a load loop. Use
`GET /v1/me`, node details, progress and word reads to validate its identity,
ownership and dataset. Validate provisioning responses against the release's
OpenAPI/Pydantic response schemas.

For production, `POST /sessions` is development-only. A dedicated account can
sign in through Clerk's documented one-use
[ticket flow](https://clerk.com/docs/nextjs/guides/development/custom-flows/authentication/legacy/embedded-email-links),
then an operator can mint a bounded token for that existing session with
[`POST /sessions/{session_id}/tokens`](https://clerk.com/docs/reference/backend-api)
and `expires_in_seconds: 3600`. Keep the backend key out of the runner.
The runner checks issuer/expiry; the API still verifies the actual signature and
authorization on every request. No authentication bypass or global session-policy
change is needed.

The runner requires scenario runtime + setup/drain budgets + five minutes of
remaining token lifetime. Default short-lived browser tokens will be rejected.
After the experiment, revoke only the dedicated test session and remove the
local token/fixture file. Retain its non-secret dataset manifest and test-owned
deck if needed for an identical comparison; never delete an ordinary user's data.
