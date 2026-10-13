# Configuration

## Policy and deployment values

Product policy lives in [config/config.yaml](../../config/config.yaml). Its loader is
[app/config.py](../../apps/api/pycil/app/config.py); domains own their policy models.
Unknown fields, duplicate YAML keys, invalid enum values, missing plans and infeasible
defaults fail validation. Policies are immutable. Restart processes after changes.

`CONFIG_PATH` selects the policy file. The default resolves relative to source;
the image sets `/app/config/config.yaml`. Credentials belong only in the environment.

## Runtime environment

[Deployment validation](../../apps/api/pycil/app/settings.py) owns this contract:

| Variable | Meaning |
| --- | --- |
| `DB_URL` | PostgreSQL application URL using `postgresql+asyncpg://`, with host and database |
| `REDIS_URL` | Explicit Redis server using `redis://` or `rediss://` |
| `CLERK_JWKS_URL`, `CLERK_ISSUER` | Required HTTP(S) signature-key endpoint and issuer |
| `CLERK_AUDIENCE` | Optional JWT audience verification |
| `CLERK_SECRET_KEY` | Required server-side identity lookup credential |
| `LLM_API_KEY`, `LLM_BASE_URL` | Required chat/structured generation provider credential and endpoint |
| `DECISION_API_KEY`, `DECISION_BASE_URL` | Required OpenRouter credential and complete Decisions endpoint |
| `ALLOWED_ORIGINS` | Optional comma-separated exact HTTP(S) origins |
| `CONFIG_PATH` | Optional product-policy path |

Service URLs reject embedded credentials. Origins also reject paths, queries and
fragments. Direct commands need exported values or uv's explicit `--env-file`.
Never print resolved credentials or put them in policy files.

`DECISION_BASE_URL` is the full request URL, such as
`https://openrouter.ai/api/alpha/decisions`; Instructor does not append a path.
`providers.vocabulary.decision_model` is the OpenRouter model ID, including its
vendor prefix. Infrastructure selects Instructor's OpenRouter Decisions transport
without stripping that prefix from the model sent to the provider.

## Policy ownership

| Group | Owner and purpose |
| --- | --- |
| `account`, `plans` | Preferences, feature grants and monthly allowances |
| `learning` | Supported question/format pairs, generation/preparation limits, evidence, Elo and FSRS |
| `generation`, `providers.vocabulary` | Word generation limits and structured/decision model policy |
| `assistant`, `models` | Conversation limits, selectable models, efforts and configured token rates |
| `library` | Tree/membership quotas and bounded scope work |
| `projections` | Bounded response composition and hydration |
| `cache` | Actor TTL |
| `http` | Streamed request body-size limit |

Controlled values serialize in lowercase `snake_case`, including plan keys, feature
names, question types, response formats and reasoning efforts. No uppercase aliases exist.
Use the policy itself for current numeric limits and rates rather than a second copy here.
Token rates are configured accounting inputs, not live pricing or invoice reconciliation.

Generation has one bounded retry policy per provider operation; SDK transport retries
are disabled. `structured_llm` passes that policy to Instructor's native retry engine,
which validates Pydantic responses and reasks with validation feedback. `decision_llm`
uses Instructor's native Decisions models and transport; its client currently has no
native retry engine, so infrastructure applies the same bounded policy around requests.
The deadline includes requests and backoff. Provider usage preserves unknown measurements
and includes failed attempts without counting cumulative reports twice. Application-owned
HTTP clients close at shutdown; their response hooks measure usage before parsing.
Retry diagnostics omit raw model output. Grading does not settle assistant allowance.
Generation prompts remain packaged in their owning modules; decision instructions live
in domain Pydantic models, without JSON-e templates.

## Compose

[scripts/compose.py](../../scripts/compose.py) derives `_DB_*` and `_REDIS_*` from canonical
URLs. Do not configure those internal keys. Loopback hosts become Docker service DNS;
remote addresses remain remote. The wrapper requires database credentials and a Redis
password. Only quiet Compose configuration validation is allowed.

Optional operator values include `API_IMAGE`, `API_HOST_PORT`, `DOMAIN`,
`CADDY_HTTP_PORT` and `CADDY_HTTPS_PORT`. The migration service imports the repository's
JSONL through a read-only mount. There is no runtime content seed configuration.
See [getting started](getting-started.md) and [deployment](operations/deployment.md).
