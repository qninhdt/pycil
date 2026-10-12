# Configuration

## Two configuration channels

Product policy is strict YAML at `config/config.yaml`. Deployment addresses and credentials
come from the environment. Do not make model/limit policy
an undocumented environment override or put credentials in YAML.

`CONFIG_PATH` selects a policy file; otherwise resolution is relative to the installed
source location, not the current shell directory. The image sets it to
`/app/config/config.yaml` and bakes the policy into the API image.
Changing environment variables does not replace that baked policy. Restart processes
after configuration changes; there is no hot-reload configuration service.

Unknown policy fields, duplicate YAML keys, malformed values, invalid enum selections,
missing plans, and infeasible defaults fail validation. Product models are frozen and
reject non-finite values. Startup errors avoid echoing raw credentials.

## Runtime environment reference

| Variable | Requirement / interpretation |
| --- | --- |
| `DB_URL` | Required; `postgresql+asyncpg://` with explicit host/database |
| `REDIS_URL` | Required; `redis://` or `rediss://` with an explicit server |
| `CLERK_JWKS_URL` | Required HTTP(S) URL for signature keys |
| `CLERK_ISSUER` | Required issuer checked on every JWT |
| `CLERK_AUDIENCE` | Optional; enables audience verification when set |
| `CLERK_SECRET_KEY` | Required; missing-user verification against Clerk |
| `ALLOWED_ORIGINS` | Optional comma-separated exact HTTP(S) origins; empty means no configured cross-origin callers |
| `INFERENCE_API_KEY`, `INFERENCE_BASE_URL` | Required model service credentials/address |
| `LEXI_DECISION_API_KEY`, `LEXI_DECISION_BASE_URL` | Required native decision service credentials/address |
| `CONFIG_PATH` | Optional policy file override |

Service URLs reject embedded credentials. Allowed origins reject paths, queries, fragments,
and embedded credentials. Include a non-default port in an origin when the browser uses it.
Never include real secrets in examples, source control, resolved Compose output, or tickets.

A direct `uv run` needs exported environment or an explicit `--env-file`; application
configuration does not load `.env` by itself. See [getting started](getting-started.md).

## Policy groups and current values

### Accounts and plans

- Default locale `en`, timezone `UTC`, translation language `vi`.
- Account `assistant.auto_approve` defaults to `false`; users change it in the Assistant panel.
- Locales and translation languages currently allow `en` and `vi`; timezone validation
  checks the system timezone catalog.
- FREE: 1,000,000 monthly units, ASSISTANT.
- PRO: 10,000,000 monthly units, ASSISTANT and ADVANCED_GRADING.

Units are internal integer accounting. Assistant rates use the fetched provider
catalog prices described below; unit totals do not reconcile provider invoices.

### Learning

`config/config.yaml` owns the pair/level matrix, defaults and limits. N defaults to 10 (1–20); K defaults to 2 (1–3); at most 60 questions/results. Free effectively uses SINGLE_CHOICE. Pro uses selected supported pairs. Answer text is limited to 8,000 characters. Activity/schedule windows remain 366/30 days and summary batches 50 IDs.

Mastery starts at Elo 600, K=32, scale 400, with a 24-hour evidence horizon. Four configured thresholds map Elo to five levels; fixed opponent ratings are configured per level. Memory uses native FSRS 6 default weights, retention .9, maximum interval 365 days, and S=1/D=5 for new all-null evidence. See [Study](modules/study.md) for selection and update behavior.

### Library

| Setting | Value |
| --- | ---: |
| Maximum physical depth | 20, Library at 0 |
| Page size | 50 default; caller `limit` 1-100 |
| Senses per deck | 1,000 |
| Children per folder | 500 |
| Active owned nodes | 2,000, excluding only Library |
| Active owned memberships | 100,000 |
| Expanded nodes per scope budget | 10,000 |
| Raw memberships per scope budget | 200,000 |
| SQL statement timeout during scope work | 3,000 ms |
| Overall scope expansion timeout | 5 seconds |

Ownership quotas and scope-work budgets are different limits. These deadlines are not
latency guarantees. The transaction-local statement timeout can also affect later SQL
within the same transaction. More details: [Library](modules/library.md).

`projections` groups bounded FE read payloads, not a table/cache/worker: maximum page
100, logical summary memberships 200,000, word IDs 30 / senses 500, context senses
100, inline sources 5, examples 2, query characters 200. Values can be lowered within
the static schema ceilings; batches fail rather than silently return partial words.

### Generation

Word generation remains inventory plus concurrent enrichment batches of up to eight Senses, requesting three usable examples per Sense. It finishes READY independently of question banks. The API supports up to 128 concurrent Word jobs and provider operations; its existing job deadline and cancellation behavior remain.

Study preparation retrieves/generates artifact banks on demand. `question_artifact_batch_size` defaults to 8, `correct_count` to 1, and `distractor_count` to 3. Contextual shortages generate at least eight artifacts. Singleton WORD_DEFINITION/WORD_TO_USAGE banks contain one row; explicit native generation extends their option arrays. Target markup and per-item validation remain native. Questions are built without inference in Pycil.

### Assistant

Current limits: 180-second SDK request timeout, 32 tool calls, 8,000 message characters, 100
context messages, 4 images of at most 10,000,000 bytes each, and 20 admitted starts per
user/minute. There is no whole-agent-turn deadline. `assistant.llm_timeout_seconds`
controls SDK network timeouts, including read inactivity, for each model request. Conversations have no automatic expiration; owners delete them explicitly.

The Assistant default is `openai/gpt-6-luna` with effort `medium`; its allowlist also
includes `google/gemini-3.8-flash` with low/medium/high effort choices.
Luna's supported effort choices are `low`, `medium`, and `high`. Lexi generation and the decision fallback use Luna with
`medium` reasoning, a 16,384-token completion budget (including reasoning), and a
120-second request timeout, after the live 8,192-token run exhausted its output limit.
`providers.lexi.max_completion_tokens` accepts up to 32,768 tokens when a reasoning
model needs more room to complete its JSON output. Jev decisions use `typesafe/jev-1.13`. Public Assistant choices come
from the allowlist, not arbitrary client model IDs; the decision-only model is
not an Assistant choice.

OpenRouter prices were fetched on 2026-10-08. Luna's base input/output/cache-read/
cache-write prices are $0.10/$0.50/$0.01/$0.125 per million tokens. The policy
preserves the existing integer unit scale: one million units equals $1 of configured
token cost. Jev input costs $0.042 per million tokens with zero output charge;
grading does not currently deduct Assistant allowance. See the
[Luna catalog](https://openrouter.ai/openai/gpt-6-luna) and
[Jev catalog](https://openrouter.ai/typesafe/jev-1.13).

Gemini 3.8 Flash's fetched input/output/cache-read/cache-write prices are
$0.75/$3.75/$0.075/$0.0416666666666667 per million tokens. Reasoning tokens use the
output rate. See the [Gemini catalog](https://openrouter.ai/google/gemini-3.8-flash).
These are the current OpenRouter catalog rates, not a guarantee of future prices.

The configured rates are the base tier. Luna input at or above 272,000 tokens uses
higher provider rates; the current meter does not implement context-tier pricing
and its unit total is not an invoice reconciliation. Actual provider cost remains
the provider's reported charge.

Backend secrets use `INFERENCE_API_KEY` and `LEXI_DECISION_API_KEY` in the private
environment. The same OpenRouter key can serve both. Chat uses
`INFERENCE_BASE_URL=https://openrouter.ai/api/v1`; the TypeSafe SDK uses
`LEXI_DECISION_BASE_URL=https://openrouter.ai/api` and appends `/v1/systemone`, as
documented in the [OpenRouter TypeSafe SDK guide](https://openrouter.ai/docs/guides/community/typesafe-sdk).
These keys never belong in the frontend environment.

### Cache and HTTP

Actor TTL is 60 seconds. The optional cache allows at most 1,000
entries and 65,536 bytes per value. Oversized values are discarded, not split into
unbounded fragments. HTTP body limit is 15,000,000 bytes, also configured in Caddy;
update both when deliberately changing this boundary.

## Compose and operator-only values

`scripts/compose.py` derives `_DB_*` / `_REDIS_*` variables from the canonical DB/Redis URLs.
Users should not configure these derived keys. Loopback hosts become Docker service
DNS inside containers; remote addresses remain remote. The wrapper requires DB username
and password and a Redis password even though runtime URL validation is less restrictive.

Optional Compose values include `API_IMAGE`, `API_HOST_PORT`, `DOMAIN`,
`CADDY_HTTP_PORT`, and `CADDY_HTTPS_PORT`. The reference file is mounted read-only.
Deploy approval and backup-check variables are described in [deployment](operations/deployment.md).
Test-only variables are described in [testing](testing.md), not used as production defaults.

## Sources

- [Strict configuration](../../apps/api/pycil/config.py), [policy](../../config/config.yaml)
- [Compose wrapper](../../scripts/compose.py), [Compose manifest](../../docker-compose.yml)
- [Policy tests](../../apps/api/tests/unit/test_product_policy.py), [configuration tests](../../apps/api/tests/unit/test_bootstrap_config.py)
