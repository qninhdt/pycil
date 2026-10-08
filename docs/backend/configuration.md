# Configuration

## Two configuration channels

Product policy is strict YAML at `config/config.yaml`. Deployment addresses, credentials,
and the reference-file location come from the environment. Do not make model/limit policy
an undocumented environment override or put credentials in YAML.

`CONFIG_PATH` selects a policy file; otherwise resolution is relative to the installed
source location, not the current shell directory. The image sets it to
`/app/config/config.yaml` and bakes the policy into the same image used by API and worker.
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
| `LEXI_CAMBRIDGE_DB_PATH` | Required existing native reference file, not a directory or an arbitrary empty SQLite file |
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
- Locales and translation languages currently allow `en` and `vi`; timezone validation
  checks the system timezone catalog.
- FREE: 1,000,000 monthly units, ASSISTANT.
- PRO: 10,000,000 monthly units, ASSISTANT and ADVANCED_GRADING.

Units are internal integer accounting. Assistant rates use the fetched provider
catalog prices described below; unit totals do not reconcile provider invoices.

### Learning

| Setting | Current default / limit |
| --- | --- |
| `questions_per_sense` | 3; allowed 1–7 |
| `max_sense_count` | 10; maximum*K <= `max_questions_per_prepare=100` |
| `formats` | SINGLE_CHOICE |
| `show_explanations` | true |
| Candidate count batch | 100 |
| Graded answer characters | 8,000 |
| Review batch / summary IDs | 100 / 50 |
| Activity / schedule window | 366 / 30 inclusive dates |
| Desired FSRS retention / maximum interval | 0.9 / 365 days |

Preparation accepts NEW/DUE/AUTO, default AUTO, and an optional maximum override.
It rejects impossible combinations instead of silently clipping questions.

`pair_levels` defines legal type/format combinations and presentation levels. `format_mix`
caps single-word and short-answer choices by the previous rating; New and Again currently
use no typed-answer upgrades when multiple-choice is available. Plan gates further restrict
effective formats. See [Study](modules/study.md) for selection details.

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

Generation targets 8 questions per supported question type. The enrichment prompt
requests exactly 5 examples per sense (the configured count); validation accepts any
nonempty list of usable examples. Question output may contain fewer or more items. Each question still requires 3 distractors.
Known generated enum and target-markup labels accept either case. Invalid individual
examples/questions are discarded, canonical duplicates are removed, and empty usable
output is retried within the native LLM budget. Existing nonempty banks are reused
without topping them up to a quota. Inventory, enrichment and question-pool generation
are the three sequential phases; every sense enrichment request runs concurrently,
then every missing sense/type pool runs concurrently. Pending fan-out tasks are
cancelled and joined before returning on error or deadline. Provider rate limits
still apply. Worker polling is every second, each attempt
has a 600-second deadline, at most 3 attempts, and a 5-second retry delay.
Lexi requests use structured outputs so native output schemas, including enum values,
are sent as the provider response format and validated by the SDK.
Question schemas require usable output without an exact batch-length constraint.
Native question content and target checks run per item during parsing; invalid answers
are never appended to the question bank. After bounded inference retries, missing
question types produce `SUCCEEDED` with stage `PARTIAL` and sanitized error
`question_pools_incomplete`; the word remains readable. Study still needs enough
eligible questions for the user's chosen preferences.

### Assistant

Current limits: 180-second SDK request timeout, 32 tool calls, 8,000 message characters, 100
context messages, 4 images of at most 10,000,000 bytes each, and 20 admitted starts per
user/minute. There is no whole-agent-turn deadline. `assistant.llm_timeout_seconds`
controls SDK network timeouts, including read inactivity, for each model request. Conversation retention is 30 days; worker cleanup runs at a 3,600-second
interval in batches of 100.

The Assistant default is `openai/gpt-6-luna` with effort `medium`; its allowlist also
includes `google/gemini-3.8-flash` with low/medium/high effort choices.
Luna's supported effort choices are `low`, `medium`, and `high`. Lexi generation and the decision fallback use Luna with
`medium` reasoning, a 16,384-token completion budget (including reasoning), and a
120-second request timeout, after the live 8,192-token run exhausted its output limit. Jev decisions use `typesafe/jev-1.13`. Public Assistant choices come
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

Actor and deck-editor TTLs are 60 seconds. The optional cache allows at most 1,000
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
