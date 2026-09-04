# decisions

The index. Every decision carries rationale, a reference tier per R5, and an
upgrade seam per R2. `judgment` means no tier 1–3 source exists and the
reasoning is stated inline. `uncalibrated` means a value must be measured before
it is trusted; the measurement that settles it is named.

Prefixes: `A` architecture · `B` learning · `C` content and supply ·
`D` hierarchy · `E` realtime · `F` messaging · `G` agent · `H` auth ·
`P` plans and credit · `I` frontend · `N` testing and CI · `O` ops ·
`Q` deliberately absent.

## 0. Preconditions — not design questions

These three are broken today and block verification of everything in this
folder. They are fixed first, independently of any decision below.

| # | Condition | Evidence | Fix |
|---|---|---|---|
| P0.1 | The CI gate has been red on `main` since 2026-08-08; the last green run was 2026-07-25. `test-web` has never passed on `main`. `Deploy` was skipped on all four failing runs, so no image has reached the registry in six weeks | `gh run list --workflow=Tests --branch=main`: four consecutive `failure` | `SESSION_PASSWORD` is required with no default in Compose and the CI job supplies none. Supply it in the workflow environment |
| P0.2 | Production refuses to boot. `validate_production_settings` requires `LEXI_REFERENCE_DATASET_FINGERPRINT` and `CENTRIFUGO_SUBSCRIBE_PROXY_SECRET`; Compose passes neither to `api` or `worker`, and the image excludes `.env` | Compose references only `LEXI_REFERENCE_DATASET_PATH`; the proxy secret is absent from `.env.example` and its Compose default is the literal the placeholder check rejects | One artefact-identity variable reaches both containers (`O5`); the proxy secret is declared and documented |
| P0.3 | Restore cannot run. `restore.sh` hard-requires `BACKUP_ID`; the `backup` service declares it nowhere, and `docker compose run` does not forward an undeclared host variable. Backup defaults its own id, so only restore breaks — the path with no second chance | Resolved `docker compose config` shows the `backup` service environment without `BACKUP_ID` | Declare it on the service |

A green gate is the baseline this redesign is verified against. Without P0.1
there is nothing to compare a change to.

## A — Architecture and topology

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| A1 | One FastAPI application, not services | One team of one, one database, one deployment. Module boundaries are enforced by tests, not by network hops | judgment — a service boundary costs a wire contract and a failure mode per call; nothing here needs independent scaling | Modules are already the split line if one is ever extracted |
| A2 | **Flat module layout**: `module/{models,service,router,schemas}.py` | The three-tier `domain/application/infra` split was enforced by import-linter contracts that are now deleted, and the most security-sensitive module (`auth`, 1,027 LOC) is already flat with no ill effect. Layering that only convention enforces is layering that drifts | judgment | A module that genuinely outgrows four files splits by **concern**, never by architectural tier |
| A3 | `policy/` holds read models more than one module reads | `UserSenseStats` is written by learning and read by content and hierarchy. A shared home is what removed the `content ↔ hierarchy ↔ learning` cycle. `policy/` may import no domain, so behaviour cannot accumulate there | judgment | — |
| A4 | Postgres is canonical. Redis is coordination, cache, and Centrifugo engine — never business state | A cache that is authoritative is a cache that loses data on eviction | `[R19]` | — |
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

## E — Realtime

Detail: [cross-cutting/realtime.md](./cross-cutting/realtime.md).

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| E1 | HTTPS for every command. **One** Centrifugo connection for server-to-client, WebSocket primary, bidirectional SSE fallback | `uni_sse` cannot subscribe after connect, and the channel model requires dynamic subscription | `[R14]`, `[R15]` | — |
| E2 | Channels: `personal:#<userId>`, `job:<jobId>`, `thread:<threadId>` | The `#` form binds the personal channel to the authenticated subject, so a client cannot widen it | `[R16]`, `[R20]` | Future `workspace:` is the same shape |
| E3 | The agent channel is **thread-scoped, not run-scoped**. `runId` travels in the payload | A run-scoped channel forces a fresh subscribe every turn, and each subscribe is an authorization round-trip | `[R17]` | — |
| E4 | **Per-namespace history policy.** `job` snapshot-shaped; `thread` bounded with a short TTL; `personal` bounded and recoverable | With one shared namespace a long agent reply evicts job frames a client still needs | `[R18]` | A separate Centrifugo deployment for `thread` is the scaling lever |
| E5 | **Two recovery layers, and both are required**: Centrifugo history, then a canonical HTTP read | Centrifugo's own documentation: history "is a cache, not your source of truth" and "can be empty, truncated, or lost at any moment" — always keep a backend fallback | `[R18]` | — |
| E6 | `partial_output` persistence is **mandatory** | The checkpointer writes at node boundaries, so a reconnect mid-call would otherwise find nothing to refetch and show a blank pane. This is the one recovery piece that must be built rather than configured | `[R18]`, `[R27]` | — |
| E7 | `recovered: false` is **expected, not exceptional**; the client refetches canonical state | A bounded buffer is sometimes outrun. `wasRecovering` says only that recovery was attempted | `[R18]` | — |
| E8 | Subscribe is **default-deny**, authorized per namespace by a backend proxy. No subscription JWTs | A valid subscription token *is* an authorization decision and short-circuits the proxy | `[R16]`, `[R17]` | Short-lived single-channel tokens if proxy load ever demands it |
| E9 | Revocation calls Centrifugo's server API. Publication is best-effort and never fails a mutation | Without revocation, a removed reader keeps receiving frames on an established subscription — channel splitting would become a security regression | `[R17]` | — |

## F — Messaging and durable jobs

Detail: [cross-cutting/messaging.md](./cross-cutting/messaging.md).

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| F1 | **Taskiq** over **Redis Streams** (`RedisStreamBroker`) | arq is in maintenance-only mode. Of the three Redis brokers only Streams has consumer groups and acknowledgement; the list broker is what arq already was | `[R21]`, `[R24]`, `[R25]` | The broker class is the swap point for NATS or RabbitMQ |
| F2 | **Ack after the durable claim** (`--ack-type when_received`) | The broker holds nothing in flight for minutes; recovery is the reaper, not redelivery | `[R21]` | — |
| F3 | **Retry off** for agent runs. Payload is `{runId}` only | Library retry restarts a task from its arguments, which is a rerun from input. A run is not idempotent: rerunning one that produced half an answer bills twice and emits garbage. Anything beyond the id in the payload lets a redelivery restart from it | `[R22]` | — |
| F4 | **Exactly one authoritative retry counter**: `attempt` on the domain row | Three counters for one concept, two of them unaware of checkpoints, is how a run gets rerun when it should have failed | judgment | — |
| F5 | Transactional outbox: state and message commit together; a relay claims with `FOR UPDATE SKIP LOCKED` | Solves exactly one problem — dual write. It does not give exactly-once, which is why consumers must be idempotent | `[R31]`, `[R35]`, `[R36]` | — |
| F6 | The relay runs **in-process** in every replica; no leader election | `SKIP LOCKED` guarantees two relays never claim one row. An external relay cannot join the producer's transaction, which recreates the dual write it exists to prevent | `[R31]`, `[R35]` | — |
| F7 | A **dedup store is needed only when the effect is append or increment.** A conditional update, a unique-key insert, or an absolute overwrite is already idempotent | Most consumers are idempotent through a domain constraint. A separate inbox table adds a second write to the hot path | `[R35]` | — |
| F8 | Each consumer **declares** its mechanism and has a test proving duplicate delivery causes no double effect | There is no generic inbox library to hide behind | judgment | — |
| F9 | The **scheduler is a separate process** | Periodic work in the worker's own slots starves when the pool is full — and the heartbeat that gates readiness is periodic work | `[R23]` | — |

## G — Agent runtime

Detail: [modules/agent.md](./modules/agent.md).

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| G1 | A Run is a **durable queued row**, claimed by a worker. Never inline in the request | Inline means the request is held for the run deadline, a client disconnect severs generation, approval needs a second stream because the first died with its request, and a deploy kills everything in flight | `[R29]` | — |
| G2 | The command **returns a handle**; tokens travel over the connection the client already has | A disconnect changes no state | `[R29]` | — |
| G3 | Agent runs take a **separate queue and worker process** | Two workload classes with service times an order of magnitude apart on one FIFO is head-of-line blocking: a grade lands behind every queued run. Routing long work to a dedicated queue with its own worker is the documented arrangement, not an optimisation. Drain windows also differ by the same order | `[R21]`, `[R22]` | Split further only on measured starvation |
| G4 | Worker concurrency (`--max-async-tasks`) **is** the global admission bound. Per-learner fairness is checked at enqueue | One knob enforced by the runtime beats two places asserting the same number. Admitting before enqueue is what keeps the queue from holding a deep backlog | `[R21]`, `[R29]` | `uncalibrated` — needs queue depth and wait time per kind |
| G5 | Claim with `FOR UPDATE SKIP LOCKED`, hold a **lease with a heartbeat**, **fence** every write | Admission alone wedges a thread when a worker dies, so a lease is needed. A lease alone lets a paused worker wake and overwrite its successor, so a fence is needed | `[R29]`, `[R31]` | — |
| G6 | Recovery is a **reaper**: lease expired → back to `queued` → another worker resumes **from the checkpoint** | Not from input. The checkpointer is the resume mechanism, so a tool that already ran has its result in state | `[R27]`, `[R29]` | — |
| G7 | Lease expiry is **not terminal** | Terminal is reached only when `attempt` is exhausted, and then it is a failure with a reason. A status meaning "the lease ran out" would be a second retry counter | judgment (follows `F4`) | — |
| G8 | **Cancellation is a column** on the run row, observed at the next yield point | Terminating a process cannot know whether the target already moved on | `[R29]` | — |
| G9 | HITL is **kept**, because the agent has destructive tools over the learner's own library | The reference design that removes approval entirely has an assistant that structurally cannot write. This one can move, publish, delete, and remove content | judgment | — |
| G10 | HITL is `interrupt()` + a **popup in the agent panel** + one resume endpoint. Approve executes; reject delivers a rejection the agent can respond to | The pause state lives in the checkpoint, which is the state machine. An action table, a TTL, an expiry reconciler, a freshness check, and an audit row add five components that chain nothing: the tool re-checks ownership when it finally runs, and Postgres holds the truth | `[R26]` | — |
| G11 | A waiting approval **holds no worker slot** | The job ends, the checkpoint persists, approval enqueues a new job. Otherwise a human lunch break occupies capacity | `[R26]`, `[R27]` | — |
| G12 | **Compaction is mandatory**, triggered by a ratio of the context window. Never split a tool call from its result | A per-message cap bounds one message; nothing bounds a thread. A long enough thread exceeds the window and the failure is at the provider | `[R30]` | — |
| G13 | **Every external string is wrapped** so the model treats it as data | Node names, deck names, and dictionary text are author-controlled and flow into tool results. A folder named like an instruction, next to a delete tool, is a real injection path | `[R37]` | — |
| G14 | Prompt caching is **prefix stability**: no timestamp or random id in the system prompt, a tool list that never changes mid-session, deterministic JSON, thinking blocks returned with tool results, compaction as the deliberate invalidation point | Cache prefix order is `tools → system → messages`, so anything unstable early invalidates everything after it | `[R30]` | — |
| G15 | Log `cache_read_input_tokens` per call | A read that is always zero is a cost bug, and nothing else surfaces it | `[R30]` | — |
| G16 | The system prompt is written **against a corpus of real ones**, not hand-written short | Shape, length, and how tools and boundaries are described are the hard parts, and there is a reference body of work | `[R39]` | — |
| G17 | **No sandbox.** The agent executes no code | Its tools are library operations and dictionary reads. A container boundary protects against a capability the agent does not have | judgment | The seam is the tool registry: code execution would need one before it could be added |

## H — Auth

Detail: [cross-cutting/auth.md](./cross-cutting/auth.md).

| # | Decision | Rationale | Ref | Seam |
|---|---|---|---|---|
| H1 | **No BFF.** The browser calls FastAPI directly on the same public origin | Same-origin is load-bearing beyond tidiness: the cookie stays first-party and the API hands the browser a realtime URL verbatim, so a separate origin makes every subscribe cross-origin | judgment | — |
| H2 | Access JWT in an `HttpOnly` `Secure` cookie for the browser; **`Authorization: Bearer` for mobile**. Both present → reject as ambiguous | One API, two credential shapes. Letting filter precedence pick an identity is how an ambiguity becomes a bypass | `[R04]`, `[R07]` | — |
| H3 | **HS256** stays | Asymmetric signing exists so a verifier cannot forge. With one verifier that property buys nothing, and it costs key distribution and rotation machinery | judgment | `tokens.py` is the only module that signs or verifies, so the algorithm is a one-file change |
| H4 | JWT validation pins the algorithm allow-list and requires `iss`, `aud`, `typ`, `sub`, `exp`, `iat` | Never trust the token's own `alg` — that is algorithm confusion. A token type claim is what stops an access token being replayed where a different purpose is expected | `[R06]`, `[R07]` | — |
| H5 | Nothing mutable goes in the token: no email, no plan, no credit balance, no membership | A token carrying authorization state is stale by construction, and staleness in an authorization decision is a security bug | `[R06]` | — |
| H6 | Revocation is a **version integer on the user row, re-read every request** | The claim is edge convenience; the row is the truth | judgment | — |
| H7 | Identity is keyed on **`(issuer, subject)`**, never on email | The provider documents that email can change and that the subject is the stable identifier. Keying on email means an email change creates a second account and abandons the learner's entire memory state | `[R13]` | Multiple providers are additional rows, not a schema change |
| H8 | Refresh is an **opaque rotating credential**; only a peppered digest is stored | The raw value never reaches persistence. Rotation is transactional under a row lock | `[R04]` | — |
| H9 | A rotated token replayed **outside a bounded grace window revokes the whole family** | Inside the window it recovers its deterministic successor, so overlapping tabs and a retry after a crash converge instead of logging the user out | `[R04]` | — |
| H10 | Refresh has **both idle and absolute** expiry | An absolute limit alone lets an abandoned session stay valid for its whole lifetime | `[R04]` | — |
| H11 | CSRF: a token on unsafe methods **plus** an exact origin check. `SameSite` is not the boundary | Cookies are attached automatically; `SameSite` is a defence, not the boundary | `[R04]` | — |
| H12 | Cookie paths are narrow: access at `/`, refresh **only** at the refresh endpoint | A refresh credential must never reach a resource route, a log, or the realtime layer | `[R04]` | — |
| H13 | The realtime connection token is a **separate short-lived token**, not the API access token | A realtime-token compromise must not be an API compromise. The realtime layer is configured with its own expected audience | `[R16]` | — |
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
| I1 | Next.js is **UI only**. The whole server-action data layer goes | Those files existed because the token lived server-side. With the browser holding a cookie they become direct calls | judgment (follows `H1`) | A narrowly justified server-rendered route is designed separately if one is ever needed |
| I2 | The API client and DTOs are **generated from the OpenAPI document** | Hand-written mirrors of server DTOs drift silently, and a second generated artefact for error codes is a second source for one contract | `[R08]` | — |
| I3 | One hand-written transport wrapper survives: credentials, CSRF, error envelope, idempotency key, request id | Cross-cutting request behaviour is not generated | judgment | — |
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
| O2 | **Caddy is the only public ingress**, with an explicit non-compression carve-out and unbuffered proxying for the realtime path | Compression buffers a realtime publication; a proxy that buffers defeats streaming entirely. The catch-all must be last or nothing after it is reachable | `[R34]` | — |
| O3 | **The web app is deployed here**, behind Caddy, sharing the API origin | Required by `H1`. Any document claiming an API-only stack is stale | judgment | — |
| O4 | **Migration is a blocking one-shot** that asserts the dictionary schema head, then applies the application schema. Nothing takes traffic against an unmigrated database | A healthy database is not a migrated database | judgment | — |
| O5 | **One variable names the reference artefact's identity** | Two names for one value, with two consumers and no assertion that they agree, means a rotation that updates one leaves work keys claiming the wrong artefact | judgment | — |
| O6 | A service with a **missing required variable fails to boot**, reporting every missing name at once | A container that starts and then rejects every request looks healthy while doing nothing | judgment | — |
| O7 | **No observability stack.** Structured logs to stdout | Seven processes for one operator. Accepted consequence, stated plainly: three values in this folder stay `uncalibrated` until it returns | judgment | Logs to stdout plus stable error codes are the seam for a scraper or an error tracker |
| O8 | Readiness is distinct from liveness, and the **worker heartbeat threshold exceeds the slowest legitimate task** plus the poll interval | Otherwise a slow-but-healthy worker is killed mid-task | judgment | — |
| O9 | **Graceful drain**: stop claiming, finish or checkpoint in flight, relay finishes its batch. `stop_grace_period` exceeds the longest acceptable drain | Lease and fence recovery is the failure path, never normal load balancing. Drain is what keeps a deploy from looking like a fleet of crashes | `[R29]` | — |
| O10 | Backup covers **both schemas in one dump**, taken with the write path stopped, and **restore is rehearsed** | Pycil stores opaque ids owned by the dictionary schema, so a schema-selective dump restores to a broken referential state. An unverified backup is the largest single operational risk | judgment | — |
| O11 | Foreign-key delete rules stay **`NO ACTION`** with hand-ordered deletion | Two schemas share one database and the cross-schema reference is a plain integer with no constraint, so a cascade cannot traverse it. Explicit cascades there would be false safety. Loud failure on a forgotten table is the property worth keeping — and it is an invariant on the checklist, not a script | judgment | — |
| O12 | A **runbook table**: situation → first move | The knowledge that a reaper is load-bearing, or that a realtime gateway warns instead of failing on a misspelt variable, is what disappears when it is not written down | judgment | — |

## Q — Deliberately absent

| # | Absent | Note |
|---|---|---|
| Q1 | Observability stack, metrics endpoint | `O7`. Three values stay `uncalibrated` as a stated consequence |
| Q2 | Nightly real-model evaluation | `N6`. Returns when there is a secret and a budget cap |
| Q3 | Story gallery in the gate | `N11` |
| Q4 | Durable run event table with a cursor | A third recovery layer covering nothing the second misses. `E5`, `E6` |
| Q5 | HITL action table, TTL, expiry reconciler, freshness check, audit row | `G10` |
| Q6 | Agent sandbox | `G17` |
| Q7 | Long-term agent memory store | The library is the durable record and the learner owns it |
| Q8 | A third plan tier | `P2`. A larger bucket first |
| Q9 | Credit reservation ledger | `P7` |
| Q10 | Per-deck settings | Session shape describes the person, not the material |
| Q11 | Architecture-enforcement contracts, module-cycle baselines, doc-path linting, generated-artefact staleness gates | Machinery whose cost exceeded the confidence it added, and one of them could not validate a forward-looking document at all |
| Q12 | Staging environment, Kubernetes manifests, second broker | `A8`, `O1`, `F1` seam |
| Q13 | Public discovery of shared decks | Publishing means link readability, not a marketplace |
| Q14 | Mobile app | Designed for by `H2`; not built |
