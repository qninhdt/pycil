# decisions

The index. Every decision carries rationale, a reference tier per R5, and an
upgrade seam per R2. `judgment` means no tier 1–3 source exists and the
reasoning is stated inline. `uncalibrated` means a value must be measured before
it is trusted; the measurement that settles it is named.

Prefixes: `A` architecture · `B` learning · `C` content and supply ·
`D` hierarchy · `E` delivery · `F` messaging · `G` assistant · `H` auth ·
`P` plans and credit · `I` frontend · `N` testing and CI · `O` ops ·
`Q` deliberately absent.

## 0. Preconditions — not design questions

These three are broken today and block verification of everything in this
folder. They are fixed first, independently of any decision below.

| # | Condition | Evidence | Fix |
|---|---|---|---|
| P0.1 | The CI gate had been red on `main` since 2026-08-08; the last green run was 2026-07-25. `test-web` had never passed on `main` | Historical `gh run list --workflow=Tests --branch=main` evidence | Removed the obsolete web-session dependency and supplied the required Compose validation values in CI; local workflow gates are green |
| P0.2 | Production must refuse to boot without a real `LEXI_REFERENCE_DATASET_FINGERPRINT`; the image does not include `.env` | `validate_production_settings` still fails closed on missing or placeholder identity | Compose now passes one `LEXI_REFERENCE_DATASET_FINGERPRINT` value to both API and worker (`O5`). The obsolete realtime proxy secret is removed by `E1` |
| P0.3 | Restore requires the operator-supplied `BACKUP_ID` to reach the backup service | `restore.sh` hard-requires `BACKUP_ID` | The `backup` service declares and receives `BACKUP_ID` |

A green gate is the baseline this redesign is verified against. Without P0.1
there is nothing to compare a change to.

## A — Architecture and topology

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| A1 | One FastAPI application, not services | One team of one, one database, one deployment. Module boundaries are enforced by tests, not by network hops | judgment — a service boundary costs a wire contract and a failure mode per call; nothing here needs independent scaling | Modules are already the split line if one is ever extracted |
| A2 | **Flat module layout**: `module/{models,service,router,schemas}.py` | The three-tier `domain/application/infra` split was enforced by import-linter contracts that are now deleted, and the most security-sensitive module (`auth`, 1,027 LOC) is already flat with no ill effect. Layering that only convention enforces is layering that drifts | judgment | A module that genuinely outgrows four files splits by **concern**, never by architectural tier |
| A3 | `policy/` holds read models more than one module reads | `UserSenseStats` is written by learning and read by content and hierarchy. A shared home is what removed the `content ↔ hierarchy ↔ learning` cycle. `policy/` may import no domain, so behaviour cannot accumulate there | judgment | — |
| A4 | Postgres is canonical. Redis is coordination and cache — never business state | A cache that is authoritative is a cache that loses data on eviction. The reference server draws the same line: Postgres is the system of record, Redis "stores only ephemeral data" | `[R40]`, `[R41]` | — |
| A5 | Lexi stays an **embedded library** owning schema `lexi`; Pycil stores opaque `sense_id` bigints with no FK | Lexi is a lazily-generating dictionary that can serve another application: own README, hermetic tests, portable schema. A service boundary would add HTTP for a library call | judgment — the boundary is a package, and it is verified by an invariant, not by a network | Its published contract is the seam if it is ever deployed separately |
| A6 | Alembic is **squashed to one baseline** | Pre-production, no data. The existing chain contains three verified churn cycles (a table created, indexed, leased, then dropped; another created then dropped; an expand/validate/enum-add split whose entire purpose is zero-downtime rollout against live data that does not exist) plus 14 raise-only downgrades | judgment | Normal incremental migrations resume from the baseline |
| A7 | `db/models.py` imports every model module explicitly | Alembic autogenerate needs every table imported. An explicit aggregator is the conventional monolith pattern and is one file to update. Every schema change in this redesign touches it, so it is a step in the migration procedure, not a hidden coupling | judgment | — |
| A8 | One environment. No staging stack | A second environment nobody operates beats nothing, and costs a second way for the stack to boot | judgment | A production Compose override is the seam |

## B — Learning engine

Detail: [modules/learning.md](./modules/learning.md).

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| B1 | **Two independent axes.** One answer emits a strength signal and a depth signal | Depth had no durable home, so depth evidence was smuggled into strength. Every symptom of that had one cause | judgment — the mechanism is verified in `modules/learning.md` | — |
| B2 | Strength is **FSRS-4.5 with published weights**, binary Again/Good | Same model family as Quizlet's Memory Score and Duolingo's HLR; the formula is public but θ is fitted on millions of sessions. FSRS is that model with the fitting already paid for, working from review #1 | `[R10]`, `[R11]`, `[R38]` | Refit own weights from `review_log` at scale with the optimizer `[R12]` — the log already records what it needs |
| B3 | **No Hard/Easy.** They stay unemitted | Hard means "the learner struggled" — a subjective report. Using it to encode a supply fact inverts the semantics, and FSRS-4.5's Hard penalty needs a weight the published vector does not carry at that index | `[R11]` | A calibrated latency signal is the seam, once telemetry exists |
| B4 | Depth is `depth_level` 0–4 plus `depth_streak` on the learner-sense row | A second axis needs durable state or it is a memoryless function of the first | judgment | — |
| B5 | **Streak of 2 to advance, one wrong to retreat.** Floor 1 | Deterministic, one variable, and the learner feels progress. `depth_level = 0` means "never assessed", so the floor cannot be 0 | judgment — a probe rate has no calibration data | Probing `depth+1` occasionally is a flag, no schema change |
| B6 | `serve_level` is **sampled from a window around** `depth_level`, not equal to it | Monotonic serving at depth 4 leaves exactly one question type forever, makes every review of a well-known word an LLM call, and concentrates rubric false-negatives on the learner's best-known words. The window improves pedagogy, cost, and grading accuracy together | judgment — varied retrieval practice; `uncalibrated` | The table is data; measuring the rubric false-negative rate re-tunes it |
| B7 | Only a serve **at** `depth_level` advances the streak. A correct answer below depth earns `Good` and moves depth not at all | Correct recall is retrieval, so stability is earned. It is not evidence at the requested depth, so depth does not advance | judgment | — |
| B8 | Failing **below** depth still retreats depth | Evidence is asymmetric: failing an easier item disproves the deeper claim; passing one does not prove it | judgment | — |
| B9 | **One question = one grade = one FSRS update** | Checkpoints, retry budgets, tier priorities, and disqualifiers were a self-invented state machine and the origin of every observed defect. Quizlet is simpler than what this replaces | judgment | — |
| B10 | A wrong answer returns the sense in a later round as an **ungraded re-ask**, at the level that was failed, once per session | Deleting checkpoints must not delete the teaching. The re-ask writes nothing: no review log, no stability, no depth | judgment | — |
| B11 | Session length is **derived**, not configured. Rounds are UI pagination | A learner sets two numbers; item count is `admitted + new + failed` and round count follows. Bounded above, no long tail | judgment | — |
| B12 | "Learned" means `status = scheduled` | The lifecycle enum already carries exactly this. Two competing predicates over `review_count` and `mastery` were rendered on one screen | judgment | — |
| B13 | `mastery` is displayed strength. Stage names are rendered from `depth_level` | Five stage names computed from a strength value promised a depth model and delivered a strength model with depth labels | judgment | — |

## C — Content and question supply

Detail: [modules/content.md](./modules/content.md).

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| C1 | Two generation events, and only one is expensive: generating a **word** is one LLM call per word forever; generating **questions** is mostly mechanical transforms of that entry | All LLM spend for content is in the first. Only one question type calls a model at preparation time | judgment — verified against the plugin set | — |
| C2 | Question supply is **per word, shared across every learner** | The pool for a sense grows and is reused, so question cost per learner declines toward zero as the user base grows | judgment | — |
| C3 | **No retrieval path ever generates.** Supply is requested ahead of need, always through a durable job | This is the dividing line of the whole design: the question read path never waits on a model call. When supply is empty the client is told, not stalled | judgment | — |
| C4 | Lexi's published contract **pins identity types and carries its own render discriminator** | Under-specification forced the consumer to cast the same logical id between three types across six sites and to rebuild a discriminator Lexi already names — defending at runtime against its own dependency | judgment | — |
| C5 | Lexi publishes `word_id_for(sense_id)` | Without it the consumer builds an entire flashcard to read one foreign key | judgment | — |
| C6 | The answer key never reaches the wire, enforced by a **per-variant field allowlist** | A blocklist of field names is defeated by a rename. This is the one content invariant with no second line of defence | judgment | — |

## D — Hierarchy

Detail: [modules/hierarchy.md](./modules/hierarchy.md).

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| D1 | One `nodes` table: `FOLDER` contains, `DECK` and `REFERENCE` are leaves. Arbitrary nesting under a depth cap | Adjacency list plus recursive CTE answers every question the product asks. A cap is what keeps traversal bounded | judgment | Flattened materialisation is the escalation if a measured SLO fails — not closure tables |
| D2 | Progress identity is global per `(learner, sense)`. **A node is a path, never an identity** | The same sense in three decks is one memory. This is what lets a learner reorganise without losing progress | judgment | — |
| D3 | **One set-based readability query** serves single-node authorization, batch deck authorization, and breadcrumbs | Three encodings of one authorization predicate is three places to over-grant, and each of the three carries a comment acknowledging the others | judgment | — |
| D4 | `REFERENCE` is the only cross-owner edge. A revoked target keeps the node and **says so** | It is not an error: someone changed their mind about sharing. Rendering it as an empty deck would be a lie | judgment | — |
| D5 | `structural_generation` fences the subtree cache; learning activity never bumps it | Redis keys embed the generation, so a stale fill cannot mask newer structure and old generations become unreachable without relying on deletion | judgment | — |
| D6 | Exact top-K in Postgres: at most `2K` rows, `ORDER BY … LIMIT K`, never load and sort all candidates | Due rank is an order-preserving key over FSRS recall, so the formula is not duplicated in SQL | judgment | — |
| D7 | Analytics is **one route per metric with an optional node scope**, not a folder route beside a `/me` route | The client already chose between them with a ternary, so the split bought nothing at the call site. Two functions per metric also had to agree by hand on what "learned" means | judgment | — |

## E — Delivery to the client

Detail: [cross-cutting/delivery.md](./cross-cutting/delivery.md).

The reference implementation is LangGraph's own Agent Server, whose default
self-hosted runtime is one process: *"single host: the API server manages the task
queue directly with no separate queue workers"* `[R40]`. Its container executes
runs inline unless `N_JOBS_PER_WORKER=0` tells it to stop claiming them `[R43]`.
Redis appears there only as *"a pub-sub broker to enable streaming real time output
from background runs"* `[R41]` — a bridge from a worker that holds no client
connection back to the API process that does. With the run executing in the
request, there is nothing to bridge.

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| E1 | **No realtime gateway.** Server-to-client delivery is SSE from the API process, plus polling for durable jobs | The gateway carried exactly one message shape — a job snapshot the client can `GET`. Its cost was a service, a config file, an edge carve-out, three secrets, a subscribe-proxy, an event table, an outbox, a relay, and a client library, all to avoid one poll. The reference server needs a pub-sub broker only because its worker cannot reach the client; ours can | `[R40]`, `[R41]`, `[R43]` | A gateway returns as an additive delivery layer if fan-out to several readers is ever needed |
| E2 | **Assistant tokens stream over SSE on the request that created the run** | This is `POST /threads/{id}/runs/stream` in the reference API, and the transport it uses is `text/event-stream` `[R42]` | — | `GET .../runs/{runId}/stream` (join) is the seam for a background run |
| E3 | Durable jobs — word generation, question supply — are **polled**: `GET /v1/jobs/{jobId}` | The reference server's own background-run guide polls `GET /threads/{tid}/runs/{rid}` and reads `status` `[R44]`. Generation is not interactive: a learner asked for a word and will read it when it exists | `[R44]` | A webhook field on the job row, which that API also carries |
| E4 | **Free-text grading is synchronous** under a hard timeout, returning a typed refusal on expiry | A deferred grade cost a pending row, a lease, a fence, a reconciler, an outbox row, and a push — to save the learner a few seconds. The refusal is honest and the learner resubmits | judgment — the timeout is `uncalibrated`; it needs measured p99 of the rubric call | The job substrate already exists if measurement says otherwise |
| E5 | **A dropped client connection cancels the run** | `cancel_on_disconnect` in the reference API, and inline execution makes it the only coherent option: the ASGI task *is* the run. The alternative is a run nothing is reading | `[R42]` | `on_disconnect: continue` needs a worker, which is `E1`'s seam |
| E6 | **No `partial_output` column.** A reload mid-answer loses that answer | The reference server does not persist partial output either: `stream_resumable` defaults to **`false`**, joining a run mid-flight states *"output is not buffered, so any output produced before joining will not be received"*, and when resumability is enabled the buffer lives in **Redis** under `RESUMABLE_STREAM_TTL_SECONDS` (default 120s) `[R42]`, `[R45]`. Their own advice on a failed rejoin is to fetch thread history — which is the checkpoint | `[R42]`, `[R45]` | A short-TTL Redis buffer, exactly as they do it. A column was the wrong shape |
| E7 | **Checkpoint at the message boundary**, not at every node: `durability="exit"` | A reload mid-run loses the turn in flight, which is accepted because one turn is short. Verified against `langgraph` 1.2.9: `durability="exit"` still writes a checkpoint at an `interrupt()` and `Command(resume=…)` continues from it, so HITL is unaffected | `[R42]`, verified by probe | `durability="async"` is a one-word change per run |


## F — Messaging and durable jobs

Detail: [cross-cutting/messaging.md](./cross-cutting/messaging.md).

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| F1 | **Taskiq** over **Redis Streams** (`RedisStreamBroker`) | arq is in maintenance-only mode. Of the three Redis brokers only Streams has consumer groups and acknowledgement; the list broker is what arq already was | `[R21]`, `[R24]`, `[R25]` | The broker class is the swap point for NATS or RabbitMQ |
| F2 | **Ack after the effect**, Taskiq's default executed-or-failed behaviour — **not** `when_received` | Acknowledging on receipt would ACK before the effect exists and lose the job on a crash. The Stream's pending-entry reclaim owns recovery instead: a message unacknowledged past `idle_timeout` (300s) is redelivered. **Supersedes the original `when_received` decision** | `[R21]` | — |
| F3 | **Job payload is the id plus its dispatch arguments** | There is no durable row to reload from, so the arguments must travel with the message. They are not credentials: a word query and a set of `(sense_id, level)` demands | `[R22]` | — |
| F4 | **No retry counter exists.** Delivery is at-least-once and the effect is idempotent at the content boundary | The `attempt` column this decision named lived on `job_tasks`, which does not exist. Lexi's uniqueness rule makes a redelivery after a committed write return the existing row rather than pay twice, and a Redis singleflight collapses concurrent identical word requests | judgment | A counter belongs with the durable row, if a durable row is ever added |
| F5 | **No transactional outbox, and no reconciler.** A publish failure is recorded as `failed` and the learner retries | The outbox existed to make a *publication* atomic with a state change, and `E1` deletes publication. Without a durable row there is nothing for a reconciler to reconcile from — so the receipt is written before the publish and corrected on failure, which is what guarantees a client always reaches a terminal state | `[R41]` | A reconciler returns with the durable row |
| F6 | **The receipt is Redis, with a 24h TTL.** It is not canonical state | **This reverses the original decision.** With no Postgres job row, Redis *is* the only record of an in-flight content job, so a Redis loss loses that work. Accepted rather than overlooked: a lost generation is retryable from the UI, and graded learning never depends on a job | judgment | The durable row is the seam |
| F7 | A **dedup store is needed only when the effect is append or increment.** A conditional update, a unique-key insert, or an absolute overwrite is already idempotent | Most consumers are idempotent through a domain constraint. A separate inbox table adds a second write to the hot path | `[R35]` | — |
| F8 | Each consumer **declares** its mechanism and has a test proving duplicate delivery causes no double effect | There is no generic inbox library to hide behind | judgment | — |
| F9 | **There is no scheduler process.** The worker owns its own heartbeat as an in-process task | **Withdrawn.** The implemented worker refreshes `worker:heartbeat` from `_heartbeat_loop` inside its own process, which is what API readiness reads, and nothing else periodic runs. Retention has a job function that nothing registers or calls | `[R23]` | A scheduler is a new process, not a config change |

## G — Assistant runtime

Detail: [modules/assistant.md](./modules/assistant.md).

Pycil's assistant is an LLM agent with a bounded tool set over the learner's own
library, plus approval on the destructive tools. That is exactly the problem
LangGraph's Agent Server solves, so its shape is adopted rather than reinvented,
and every deviation below is named with a reason.

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| G1 | A turn is **executed inline in the request** that started it, with **no Run row** | The reference server's default self-hosted runtime is one process managing its own queue, and its image executes runs in-process unless told to stop claiming them. A turn is a few tool calls and one to three model calls | `[R40]`, `[R43]` | A background queue plus a worker entrypoint, which is their split mode |
| G2 | **Withdrawn: there is no durable Run row.** The checkpoint is the only per-turn durable state | The row existed to make a later background queue a config change. It was dropped in migration `0007`, and nothing was lost: the checkpoint already holds everything a resume needs, and a row nothing reads is a second source of truth for one question | `[R40]`, `[R43]` | Reintroducing the row is the precondition for the background queue |
| G3 | **No fence and no reaper.** A Redis **turn lease** does exist, bounded per learner | Verified absent from the reference server: no environment variable containing HEARTBEAT or SWEEP exists in either published reference. The lease is not the fence this decision rejected — it is a resource bound so one learner cannot run two turns past the admission gate at once, and it expires on its own TTL so a killed process cannot lock a learner out. Correctness stays on PostgreSQL's unique ledger key | `[R44]`, `[R45]` | — |
| G4 | **One active turn per learner**, a Redis lease, answering `409` | The original decision scoped this per Thread via a unique partial index on a row that no longer exists. Per *learner* is the bound that matters: two turns on two threads overspend exactly as much as two on one | `[R42]` | — |
| G5 | Concurrency is bounded **per learner at admission**, not by a worker pool | With no pool there is no `N_JOBS_PER_WORKER` to set. A per-learner bound is what keeps one learner from occupying the API's capacity | judgment — `uncalibrated` | Their per-worker job cap is the seam |
| G6 | **Withdrawn: there is no cancel endpoint.** A client disconnect cancels the turn | `E5` already makes the ASGI task the turn, so a disconnect *is* cancellation and the request is cancelled. With no run row there is no `cancel_requested_at` to poll and no id to address a cancel at | `[R42]` | A cancel endpoint returns with the run row |
| G7 | Status is **derived from the checkpoint**: `interrupted` when a pending interrupt exists, `idle` otherwise | The six-value vocabulary described a run row's status column. With no row, five of those values describe something nothing records, and inventing columns to hold them would be a second counter wearing a name | `[R42]` | — |
| G8 | **HITL is kept**, because the agent has destructive tools over the learner's own library | Approval is `interrupt()` inside the tool node; the pause state is `ThreadState.interrupts` read from the checkpoint. No action table, no TTL, no expiry reconciler, no freshness check, no audit row — five components in front of state the checkpointer already holds | `[R26]`, `[R42]` | — |
| G9 | Approval resumes on a **second request**, not a held one: `POST /v1/assistant/runs/{runId}/resume` → `Command(resume=…)` | The first request ends at the interrupt, so a waiting decision occupies nothing — no worker slot *and* no open connection. Approve executes the tool; reject delivers a refusal the agent can answer | `[R42]` | — |
| G10 | Decisions are **their four**: `approve · edit · reject · respond` | The installed middleware already accepts all four; Pycil allowed two. `edit` is the one that matters for a destructive tool — correcting a target beats rejecting and re-asking | `[R26]` | — |
| G11 | The checkpointer **owns its own schema** via `setup()` | Its ten migrations are published and versioned by the library. Hand-copying the DDL into a Pycil migration means a library upgrade silently disagrees with the tables it is given | `[R27]` | — |
| G12 | **Compaction is mandatory**, triggered by a ratio of the context window. Never split a tool call from its result | A per-message cap bounds one message; nothing bounds a thread. A long enough thread exceeds the window and the failure is at the provider | `[R30]` | — |
| G13 | **Every external string is wrapped** so the model treats it as data | Node names, deck names, and dictionary text are author-controlled and flow into tool results. A folder named like an instruction, next to a delete tool, is a real injection path | `[R37]` | — |
| G14 | Prompt caching is **prefix stability**: no timestamp or random id in the system prompt, a tool list that never changes mid-session, deterministic JSON, thinking blocks returned with tool results, compaction as the deliberate invalidation point | Cache prefix order is `tools → system → messages`, so anything unstable early invalidates everything after it | `[R30]` | — |
| G15 | Log `cache_read_input_tokens` per call | A read that is always zero is a cost bug, and nothing else surfaces it | `[R30]` | — |
| G16 | The system prompt is written **against a corpus of real ones**, not hand-written short | Shape, length, and how tools and boundaries are described are the hard parts, and there is a reference body of work | `[R39]` | — |
| G17 | **No sandbox.** The agent executes no code | Its tools are library operations and dictionary reads. A container boundary protects against a capability the agent does not have | judgment | The seam is the tool registry: code execution would need one before it could be added |
| G18 | **No assistant registry, no versions, no store, no crons, no stateless runs, no A2A, no MCP surface** | Their API carries 49 paths because it is a platform hosting arbitrary graphs for arbitrary tenants. Pycil has one graph, one tool set, one tenant model — `assistant_id` would be a column with one value | `[R42]` | Each is an additive resource on the same shape |


## H — Auth

Detail: [cross-cutting/auth.md](./cross-cutting/auth.md).

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| H1 | **No BFF.** The browser calls FastAPI directly and sends Clerk's token as a bearer header | The UI layer proxies nothing and holds no credential of its own, so there is no server-side token custody to secure | judgment | — |
| H2 | **One credential shape: `Authorization: Bearer`.** The legacy cookie is not read | Accepting two credential channels made "which identity is this?" ambiguous, and an ambiguity in identity resolution is how a bypass is built. Clerk's browser SDK sends the bearer header itself | `[R04]`, `[R07]` | — |
| H3 | **Clerk signs and validates sessions.** Pycil has no signing path and no fallback | A local fallback would mean a second issuer whose tokens this service accepts — which is the thing verification exists to prevent. A Clerk outage fails closed | judgment | — |
| H4 | Verification pins the algorithm allow-list to RS256 and validates issuer, audience and expiry when configured | Never trust the token's own `alg` — that is algorithm confusion. A token whose header names a symmetric algorithm must not be checked against public key material | `[R06]`, `[R07]` | — |
| H5 | Authorization decisions use the **internal UUID**, never the Clerk subject or a claim | A verified subject is an authentication fact, not an authorization one. Every route checks ownership or readability independently of having authenticated | `[R06]` | — |
| H6 | **Withdrawn: there is no token version and no per-request revocation check.** | Clerk owns session lifetime and revocation. Reimplementing them here would be a second source of truth for the same question, and the row this decision re-read on every request no longer exists | judgment | A local revocation list returns only with a local issuer |
| H7 | Identity is keyed on the **Clerk subject**, never on email | The subject is the stable identifier. Keying on email means an email change creates a second account and abandons the learner's entire memory state | `[R13]` | Multiple providers are additional columns, not a schema change |
| H8 | **Withdrawn: Pycil stores no refresh credential.** Clerk owns refresh | There is no refresh endpoint, no digest to store and no rotation to make atomic | `[R04]` | — |
| H9 | **Withdrawn: no replay window and no family revocation** | They existed to make rotating refresh credentials safe. With Clerk issuing sessions there is nothing here to replay | `[R04]` | — |
| H10 | **Withdrawn: Pycil sets no session lifetime** | Clerk's session policy is the policy. A second expiry here could only disagree with it | `[R04]` | — |
| H11 | **Withdrawn: there is no CSRF surface.** | CSRF exists because browsers attach cookies automatically. A bearer header is attached explicitly by application code, so a cross-site request carries no credential | `[R04]` | — |
| H12 | **Withdrawn: Pycil sets no cookie** | Follows `H2`. There is no refresh path to narrow | `[R04]` | — |
| H13 | **No separate realtime token.** The SSE stream is an ordinary authenticated route under the same bearer header | `E1` deletes the gateway, and with it the only consumer of a second token | `[R40]` | A gateway would reintroduce it |
| H14 | Errors are **RFC 9457 Problem Details** | The current standard for HTTP error shape, and a generated client derives the error enum from the schema rather than a second generator maintaining a copy | `[R08]` | — |

## P — Plans and credit

Detail: [modules/account.md](./modules/account.md).

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| P1 | **Charge what cannot be reused; give away what enriches the commons** | Generating a word or a question serves every future learner, so charging for it taxes the contribution the product depends on. Grading a learner's own writing and running their agent turn serve exactly one person | judgment | — |
| P2 | **Two tiers, Free and Pro, plus a credit top-up pack** | There are not enough separately expensive features to justify a third feature tier. Credit is consumable and usage varies widely, so a power user needs a way to buy more without waiting for a period to roll | judgment | A third tier is a larger bucket, not new features |
| P3 | **Library, tree, subtree study, review volume, deterministic grading, publishing, and export are free and unlimited** | The switching cost is the library plus the memory state. Capping either attacks the retention mechanism, and capping review volume kills the habit | judgment | — |
| P4 | Studying **a whole folder including nested subtree** is free | Cost is identical to studying one deck — the same indexed top-K. Gating it would make a free learner avoid building a tree, which is the one structure that holds them | judgment | — |
| P5 | **Credit gates depth 4 and the agent, and nothing else** | One mechanism rather than a feature flag beside a meter. Almost everything else costs nothing to serve | judgment | — |
| P6 | **One credit pool**, denominated in token work, displayed with an estimate in human units | Two separate allowances are clearer on a pricing page and worse for the user: an unused agent allowance should become writing checks. Denominating in currency breaks when a provider reprices | judgment | A future feature that costs credit needs no new meter |
| P7 | **Charge at completion, not by reservation.** A positive balance is checked at submit | Reserve/settle/release needs a state machine on the ledger. Charging at completion means an overshoot of at most one operation, bounded by the concurrency limit — and a provider failure costs the learner nothing | judgment | — |
| P8 | Debits are **append-only with a unique key on (kind, reference)** | The effect is an increment, so a retried settle must not double-charge. A unique index on the domain table is the mechanism, not an inbox | `[R35]` | — |
| P9 | The monthly grant **resets by elapsed time**, not by a scheduled job | A period start on the row plus a lazy roll on the next debit is self-healing. A cron that resets balances is a cron whose failure is a billing incident | judgment | — |
| P10 | Exhausting credit **degrades along the existing supply-shortfall path**: the sampler stops offering depth 4 and serves lower | No new state machine, no punished learner, no broken session. Strength still advances; only the top rung pauses | judgment (follows `B6`, `B7`) | — |
| P11 | Word generation is **never charged**, rate-limited per day by plan as abuse control | It is the largest single LLM cost and it goes into the shared dictionary. A free learner is therefore nearly free to serve and is a source of data | judgment | — |
| P12 | Pro price, Free grant, and Pro grant are **`uncalibrated`** | They need the measured token cost of one depth-4 grade, one agent turn, and the rubric's false-negative rate — which governs how much credit is spent on grades that had to be redone. Observability was deliberately dropped (`O7`), so these stay `judgment` until it returns | judgment · `uncalibrated` | — |

## I — Frontend

Detail: [modules/web.md](./modules/web.md).

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| I1 | Next.js is **UI only**. The whole server-action data layer goes | Those files existed because the token lived server-side. With Clerk's SDK holding the session in the browser they become direct calls | judgment (follows `H1`) | A narrowly justified server-rendered route is designed separately if one is ever needed |
| I2 | The API client and DTOs are **generated from the OpenAPI document** | Hand-written mirrors of server DTOs drift silently, and a second generated artefact for error codes is a second source for one contract | `[R08]` | — |
| I3 | One hand-written transport wrapper survives: the Clerk bearer header, error envelope, request id | Cross-cutting request behaviour is not generated | judgment | — |
| I4 | Stage names render from **`depth_level`**, and the band table has **one owner** | The table existed in four places, one of them a hand copy no generator read and no gate checked | judgment (follows `B13`) | — |
| I5 | The client session machine mirrors only what the server still has | Rounds are pagination, so the machine loses checkpoint, retry, and tier state with the server | judgment (follows `B9`, `B11`) | — |

## N — Testing and CI

Detail: [ops/testing.md](./ops/testing.md), [ops/cicd.md](./ops/cicd.md).

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| N1 | **A named invariant checklist, not a coverage number** | Test code roughly equal to production code is a verification program, not confidence. But cutting to a handful of contracts violates R4. A checklist is checkable in a way a percentage is not | judgment | — |
| N2 | Three scopes: unit, integration on real dependencies via containers, and **one golden journey** end to end | A test that brings up its own dependency means "unreachable" is a real fault rather than a forgotten setup step | `[R33]` | — |
| N3 | **Fail closed.** A test that cannot reach its dependency fails; it never skips | A skipped test reporting green is worse than a failing one because it looks like coverage | judgment | — |
| N4 | Assertion and **measurement** are separate. A real-model evaluation never gates | It measures something that varies between identical runs, so gating on it makes the gate a coin flip | judgment | Re-add as a manual or scheduled trend once there is a budget to cap |
| N5 | A **scripted deterministic provider** is kept | It exercises the real client, streaming parser, tool dispatch, and policy path with only the model's choices fixed. Without it every agent-behaviour test is billable, flaky, or both | judgment | — |
| N6 | **Two workflows**: a PR gate and a manual deploy. No nightly | The nightly evaluation skipped its only real work on every sampled run because the repository holds no provider secret — a green badge for work that never ran | judgment | — |
| N7 | Every PR step is **runnable locally with one command** | A step that only exists in CI is a step nobody can debug | judgment | — |
| N8 | **Build once, promote by digest** | Rebuilding at deploy means the artefact tested is not the artefact deployed. A tag can be moved; a digest cannot | judgment | — |
| N9 | Coverage floors and test-count floors are **deleted** | The count floors rest on a premise measurement falsifies: no runner here reports zero tests with a success exit code. The coverage numbers were also declared twice, in a workflow and in a second script nothing executes | judgment | — |
| N10 | Cross-repository verification of the pinned dictionary library is a **documented procedure**, not a script | Its one non-duplicated capability was running the sibling suite. That is a step in a bump procedure | judgment | — |
| N11 | Component behaviour is proven in the golden journey or in unit tests of pure logic. **No story gallery in the gate** | The current gallery asserts nothing: its accessibility check is set to report-not-fail, its assertion runner is not installed, and no story carries an assertion | judgment | Re-add with a runner if component states ever need per-state assertions |

## O — Ops

Detail: [ops/devops.md](./ops/devops.md).

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| O1 | Docker Compose, one VPS, one compose file plus a production override | No orchestrator to operate, one file to read, and a second compose project can run beside the live one for a rehearsal | judgment | Container-per-process, env-only config, and stdout logs are what keep an orchestrator a config change |
| O2 | **Caddy is the only public ingress**, with an explicit non-compression carve-out and unbuffered proxying for the SSE routes | Compression buffers a token stream; a proxy that buffers defeats streaming entirely. The carve-out now names Pycil's own SSE paths rather than a gateway's. The catch-all must be last or nothing after it is reachable | `[R34]` | — |
| O3 | **The web app is deployed here**, behind Caddy, sharing the API origin | Required by `H1`. Any document claiming an API-only stack is stale | judgment | — |
| O4 | **Migration is a blocking one-shot** that asserts the dictionary schema head, then applies the application schema. Nothing takes traffic against an unmigrated database | A healthy database is not a migrated database | judgment | — |
| O5 | **One variable names the reference artefact's identity** | Two names for one value, with two consumers and no assertion that they agree, means a rotation that updates one leaves work keys claiming the wrong artefact | judgment | — |
| O6 | A service with a **missing required variable fails to boot**, reporting every missing name at once | A container that starts and then rejects every request looks healthy while doing nothing | judgment | — |
| O7 | **No observability stack.** Structured logs to stdout | Seven processes for one operator. Accepted consequence, stated plainly: three values in this folder stay `uncalibrated` until it returns | judgment | Logs to stdout plus stable error codes are the seam for a scraper or an error tracker |
| O8 | Readiness is distinct from liveness, and the **worker heartbeat threshold exceeds the slowest legitimate task** plus the poll interval | Otherwise a slow-but-healthy worker is killed mid-task | judgment | — |
| O9 | **Graceful drain**: the API stops accepting, finishes assistant runs in flight, and the domain worker stops claiming. `stop_grace_period` exceeds the longest acceptable drain on each | Inline execution moves this constraint onto the API: a deploy must not sever a turn a learner is reading. The reference server's equivalent knob is `BG_JOB_SHUTDOWN_GRACE_PERIOD_SECS`, default 180s, and its own guidance is to raise it to the typical run duration | `[R45]` | — |
| O10 | Backup covers **both schemas in one dump**, taken with the write path stopped, and **restore is rehearsed** | Pycil stores opaque ids owned by the dictionary schema, so a schema-selective dump restores to a broken referential state. An unverified backup is the largest single operational risk | judgment | — |
| O11 | Foreign-key delete rules stay **`NO ACTION`** with hand-ordered deletion | Two schemas share one database and the cross-schema reference is a plain integer with no constraint, so a cascade cannot traverse it. Explicit cascades there would be false safety. Loud failure on a forgotten table is the property worth keeping — and it is an invariant on the checklist, not a script | judgment | — |
| O12 | A **runbook table**: situation → first move | The knowledge that a stuck job needs a named query, or that the API's drain window bounds a deploy, is what disappears when it is not written down | judgment | — |

## Q — Deliberately absent

| # | Absent | Note |
|---|---|---|
| Q1 | Observability stack, metrics endpoint | `O7`. Three values stay `uncalibrated` as a stated consequence |
| Q2 | Nightly real-model evaluation | `N6`. Returns when there is a secret and a budget cap |
| Q3 | Story gallery in the gate | `N11` |
| Q4 | Durable run event table with a cursor | The canonical read plus the checkpoint covers everything it would. `E2`, `E6` |
| Q5 | HITL action table, TTL, expiry reconciler, freshness check, audit row | `G8` |
| Q6 | Agent sandbox | `G17` |
| Q7 | Long-term agent memory store | The library is the durable record and the learner owns it. The reference server's cross-thread `store` is the shape if it is ever wanted |
| Q8 | A third plan tier | `P2`. A larger bucket first |
| Q9 | Credit reservation ledger | `P7` |
| Q10 | Per-deck settings | Session shape describes the person, not the material |
| Q11 | Architecture-enforcement contracts, module-cycle baselines, doc-path linting, generated-artefact staleness gates | Machinery whose cost exceeded the confidence it added, and one of them could not validate a forward-looking document at all |
| Q12 | Staging environment, Kubernetes manifests, second broker | `A8`, `O1`, `F1` seam |
| Q13 | Public discovery of shared decks | Publishing means link readability, not a marketplace |
| Q14 | Mobile app | Designed for by `H2`; not built |
| Q15 | Realtime gateway, subscribe proxy, channel namespaces, per-namespace history | `E1`. One message shape did not justify a service, and the reference server needs its pub-sub only to bridge a worker to a client |
| Q16 | Transactional outbox, event table, relay | `F5`. Publication is what an outbox made atomic, and there is no publication |
| Q17 | Assistant registry, assistant versions, cross-thread store, crons, stateless runs, batch runs, A2A, MCP surface | `G18`. Present in the reference API because it is a multi-tenant platform for arbitrary graphs; Pycil has one graph |
| Q18 | Agent worker process, its queue, its drain window | `G1`. Returns as their split mode: one entrypoint, no schema change |
