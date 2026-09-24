# removed

What this redesign cuts, and why. `Source` says what is being removed from where:

| Source | Meaning |
|---|---|
| `code` | Exists in the current codebase |
| `notes` | Exists in a root design document |
| `infra` | Compose, CI configuration, scripts |
| `docs` | Exists in a documentation file |

Recorded at **section level**, not line by line. LOC is given only where it was
measured; where it was not, the cell is empty rather than invented.

Under `R0` most of this is not "deleted" but **not re-authored**: a file written
fresh from requirements simply does not contain it. Two groups are genuinely
destructive and are marked **`DESTRUCTIVE`**: dropping a table and dropping a
column.

`docs/` and `plans/` are **kept** — see the documentation section below.

## Learning engine

| # | Source | Item | Why removed | Replaced by | LOC |
|---|---|---|---|---|---|
| 1 | code | Checkpoint state machine: required-checkpoint count, retry budget, four-tier round priority, disqualifier, open-checkpoint, open-failed-round, retries-used | A self-invented state machine and the origin of every observed learning defect. Not Quizlet, not Anki, not FSRS, and not a selling point — the product it was written to beat is simpler | One question = one grade, plus an ungraded re-ask `B9`, `B10` | |
| 2 | code | Table `session_sense_attempts` **`DESTRUCTIVE`** | Existed to collapse two checkpoints into one memory update. With one grade per answer there is nothing to collapse | A per-session key on the response row `B9` | |
| 3 | code | `user_sense_stats.buried_until` **`DESTRUCTIVE`** | Three read sites, no production writer. A filter for a state nothing creates | Nothing — the requirement never existed | |
| 4 | code | The mastery-band probability table keyed on strength | The mechanism was never the defect; keying it to a strength proxy with no memory of depth was. Sampling from a memoryless function of strength is what made depth a coin flip | The same machinery keyed on `depth_level` `B6` | |
| 5 | code | The component whose sole job was to warn a learner that a correct answer would be recorded as a miss | It existed to apologise for a defect. Under `B7` a correct answer is never recorded as a miss, so there is nothing to warn about | Nothing | |
| 6 | code | Two competing definitions of "learned", both rendered on one screen | One required a review to have happened; the other also accepted any nonzero strength. Same learner, two numbers | `status = scheduled` `B12` | |

## Assistant runtime

| # | Source | Item | Why removed | Replaced by | LOC |
|---|---|---|---|---|---|
| 7 | code, infra | Assistant worker process and queue | A dedicated process, lease, fence, heartbeat, reaper, and drain window for work the API can execute directly | Inline Run execution with a durable row `G1`–`G3` | |
| 8 | infra, code | Realtime gateway, tokens, channels, subscribe proxy, publication adapters | One pushed job snapshot did not justify a service and authorization protocol | Job polling plus direct assistant SSE `E1`–`E3` | |
| 9 | code, notes | Durable run-event table, cursor endpoint, and `partial_output` | Checkpoints and canonical Run/Thread reads already recover terminal or interrupted state; partial streaming is deliberately transient | Canonical reads after connection loss `E5`, `E6` | |
| 10 | code | HITL: action table as a state machine, a dedicated confirm endpoint, action time-to-live, an expiry reconciler, a checkpoint-freshness check | The pause state lives in the checkpoint, which **is** the state machine. Five components chaining nothing: the tool re-checks ownership when it finally runs, and a paused run holds no worker slot so nothing needs expiring | `interrupt()`, a popup, one resume endpoint `G10` | |
| 11 | code | HITL action audit rows | Postgres holds the state and the popup is the safety mechanism. An audit row blocks nothing | Nothing `G10` | |
| 12 | code | Per-turn assistant cost knobs: monthly budget, estimated cost per thousand tokens, requests per minute | Superseded rather than dead. A budget expressed in currency breaks when a provider reprices, and a request rate is not what is being spent | The credit ledger `P5`–`P9` | |
| 13 | code | A global concurrency constant asserted in application code | One global number does not stop one learner consuming API capacity | Per-learner admission `G5` | |

## Messaging

| # | Source | Item | Why removed | Replaced by | LOC |
|---|---|---|---|---|---|
| 14 | code | The previous job library | In maintenance-only mode — critical security fixes only. Its Redis queue also has **no acknowledgement**, which is why a reconciler ran every minute to compensate | Redis Streams with consumer groups `F1`, `[R25]` | |
| 15 | code | Task status meaning "the lease ran out" **`DESTRUCTIVE`** | Every transition writes success, failure, or requeued; the lease-exhaustion path writes failure with a reason. A status for it would be a second retry counter wearing a different name | `attempt` on the row, and requeue is not terminal `F4`, `G7` | |
| 16 | code | `revoked_at` on the interest row **`DESTRUCTIVE`** | Two read predicates, no production writer. Revocation is done by clamping the expiry, and a migration comment records that no row ever carried it | Expiry clamping, one mechanism | |
| 17 | code | `schema_name` on the event row **`DESTRUCTIVE`** | Never read. The version string that is consumed lives inside the payload — the column is a second, unread copy | The payload field | |
| 18 | code | Two re-export layers over the job contract | The outer layer has **zero importers**; the inner one is bypassed by five modules importing the source directly. A facade nothing uses, in front of a facade nothing honours | Direct import of the contract | |
| 19 | code | Two near-identical worker context types bridged by a cast | One shape with optional keys covers both | One type | |
| 20 | code | Periodic work inside the worker pool | Heartbeat, redispatch reconciliation, and retention must run even when job slots are full | **Superseded.** No scheduler was built; the worker refreshes its own heartbeat in-process, and no other periodic work runs | |

## Content and dictionary boundary

| # | Source | Item | Why removed | Replaced by | LOC |
|---|---|---|---|---|---|
| 21 | code | Casts of the same logical identifier between three types, wrapped in a runtime handler | The consumer was defending at runtime against its own dependency's under-specification | Identity types pinned in the contract `C4` | |
| 22 | code | A type ladder rebuilding the question-shape discriminator | The library already names its shapes; the consumer held a second copy that drifts, and a new shape became a runtime failure instead of a type error | The contract carries the discriminator `C4` | |
| 23 | code | Constructing a whole presentation object to read one foreign key | The library knows the owning word and did not publish it | `word_id_for` `C5` | |
| 24 | code | Table `deck_attributes` **`DESTRUCTIVE`** | Written on every deck creation, its only column never read — a migration comment states it "simply stops being read". Session shape describes the person, not the material | Per-learner settings `Q10` | |
| 25 | code | A deck-creation pass-through with no production caller | Two routes to one operation; the other is the one used | The hierarchy operation | |
| 26 | code | Two contract methods with no caller: one implemented only by a test double, one superseded by a fenced variant | A published method nothing calls is a promise nobody asked for | Nothing | |

## Auth

| # | Source | Item | Why removed | Replaced by | LOC |
|---|---|---|---|---|---|
| 27 | code | Identity keyed on email | The provider documents that email changes and that the subject is stable. Keying on email means an email change creates a second account and abandons the learner's memory state | The Clerk subject `H7`, `[R13]` | |
| 28 | code | The universal BFF: sealed session cookie, credential forwarding, a proxy route per surface | It existed for one reason — the token lived server-side. Clerk's SDK holds the session in the browser, so the reason is gone | Direct calls with a bearer header `H1`, `H2` | ~1,334 |
| 29 | code | An unreachable branch in refresh coordination | The encoder produces two outcomes and the decoder raises on anything else; the third branch cannot be reached | Nothing — refresh is Clerk's | |
| 30 | code | A capability flag hardcoded to one value, read by nothing | A flag with one value is a constant with extra steps | Nothing | |

## Superseded during execution

These were **specified by this folder and then not built** — or built and dropped.
They are not code that existed before the redesign. They are recorded because a
design document that silently loses a decision cannot be audited, and because each
one changed a guarantee a reader may still be relying on.

| # | Item | Why it did not survive | What holds instead |
|---|---|---|---|
| 31 | Pycil-issued HS256 access tokens, rotating refresh sessions, cookie credentials, token version, CSRF | The Clerk decision replaced the local issuer. Every mechanism here existed to make a local issuer safe — with no local issuer there is nothing to rotate, revoke or bind | Clerk verification and a subject→UUID mapping `H2`–`H12` |
| 32 | The `assistant_runs` table and its run-status vocabulary | A row nothing read, kept only to make a future background queue a config change. The checkpoint already holds everything a resume needs, so the row was a second source of truth for one question | Checkpoint state, plus a Redis turn lease for the per-learner bound `G1`, `G2`, `G7` |
| 33 | The `job_tasks` table: claim, `attempt` counter, interest rows, dispatch reconciliation | Nothing reconciled from it, and the receipt clients poll is Redis. Keeping both would be two records of one job | The owner-scoped Redis receipt with a 24h TTL `F4`–`F6` |
| 34 | A scheduler process | Never built. Its only indispensable duty — the heartbeat readiness reads — is an in-process task in the worker | `_heartbeat_loop` in the worker entrypoint `F9` |

**The cost of 32–34 together.** With no run row, no job row and no scheduler, there
is no reconciliation anywhere in the system: a lost content job is lost, and the
learner's retry is the recovery. That is the accepted trade — graded learning never
depends on a job — but it is a real reduction from what this folder originally
promised, and [cross-cutting/messaging.md](./cross-cutting/messaging.md) §4 and §6
state it rather than leaving it to be discovered.

## Frontend

| # | Source | Item | Why removed | Replaced by | LOC |
|---|---|---|---|---|---|
| 31 | code | Hand-written mirrors of server request and response types | A mirror drifts silently: nothing fails, the two just stop meaning the same thing | Generated from the OpenAPI document `I2` | ~844 |
| 32 | code, infra | A second generator producing an error-code table, plus its staleness gate | Two generators for one contract, and a gate whose only job is to notice they diverged. The table was in fact stale — a status code had changed and shipped past it | The generated client `H14`, `I2` | |
| 33 | code | Client-side round arithmetic, checkpoint index, retry counter | A second implementation of scheduling the server owns | Server-named state `I5` | |
| 34 | code | A story gallery in the gate | Asserted nothing: no assertion runner installed, its accessibility check set to report-not-fail, no story carrying an assertion. Meanwhile a testing document claimed it owned assertions that the browser layer was supposed to own | The golden journey, or unit tests of pure logic `N11` | ~1,830 |
| 35 | code, infra | A design-system lint | Its own header listed what it could not catch: contrast, anything outside two directories, composed class names, token misuse, dark-mode parity. A green gate reading as "the design system holds" is the failure mode | Nothing. The discipline it documented is inherited by review | |
| 36 | code | Unreferenced component-registry surface | Registry surface, not authored code. Fresh authoring pulls fewer parts | Fewer parts | 635 |

## Testing and CI

| # | Source | Item | Why removed | Replaced by | LOC |
|---|---|---|---|---|---|
| 37 | code, infra | Architecture-enforcement contracts and their module-cycle baseline | A baseline is a snapshot of the current structure, and a redesign invalidates a snapshot on its first commit. One baseline still named a module that no longer existed, and the checker compared only cycles — so a vanished module was silent | The invariant checklist `N1` | |
| 38 | infra | Documentation path linting | Covered a fraction of the documents, and its single live failure was a citation of a deliberately untracked file. It cannot validate a forward-looking document at all | A self-contained folder `R0` | |
| 39 | infra | A second CI runner holding test-count and coverage floors | Referenced by nothing executable. Its premise — that a collection error yields zero tests and a success exit — is **falsified by measurement**: every runner here exits non-zero. Its coverage numbers were also declared verbatim in the workflow | Nothing; and the workflow's own count assertions go with it `N9` | 307 |
| 40 | infra | The nightly real-model evaluation | Skipped its only real work on **every** sampled run because the repository holds no provider secret. A green badge for work that never ran | A recorded measurement when there is a budget `N4`, `N6` | 152 |
| 41 | code | Tests asserting on configuration files by substring | A test that greps a deployment file is a lint on a file outside its scope, and it breaks on reformatting. One asserted entirely on compose and deploy scripts | Behaviour tests, and boot-time validation `O6` | |
| 42 | code | Parametrised cases with no distinct failure mode | Ten literals through one code path; four whitespace variants of one normalisation call | One case per branch | |
| 43 | code | Tests whose subject is a generated artefact's bytes | The fingerprint changed while the content did not — the gate fires on regeneration, not on divergence | One generator `I2` | |
| 44 | code | A twelve-to-one test-to-production ratio on a channel-name builder | 282 lines over a 19-line function, four unrelated concerns in one file, two of them asserting on files outside the module | The invariant that matters: the builder produces a name the authorizer accepts | |
| 45 | code | Twelve of thirteen browser specs | Thirteen specs are not thirteen times the confidence; they are thirteen times the maintenance. And they had not executed at all | One golden journey `N2` | ~2,300 |

## Operational layer

| # | Source | Item | Why removed | Replaced by | LOC |
|---|---|---|---|---|---|
| 46 | code | In-memory metrics counters behind an internal endpoint | Lost on restart, per-replica, and nothing scraped them. A metric nobody reads is a metric that cannot be trusted when it is finally read | Structured logs; the observability stack is deferred with its cost stated `O7` | |
| 47 | infra | Two names for one artefact identity | Same value, same length, two consumers, no assertion that they agree — so a rotation updating one leaves work keys claiming the wrong artefact. And the one that production requires never reached the container | One variable `O5`, `P0.2` | |
| 48 | infra | A release script pinned to a branch that no longer exists | Fails at preflight, so it has not run. Bumping a pinned dependency is a procedure, not a script | A documented procedure `N10` | 130 |
| 49 | infra | A configuration knob for a second database | One host, one Postgres. A seam with nothing on the other side of it | Nothing | |
| 50 | infra | A settings field whose only reader is the validator checking it is set | The real consumers read the environment variable directly | Nothing | |
| 51 | infra | Five compose variables with no reader and no requirement | Injected into a process that never reads them, or present in no template | Nothing | |
| 52 | infra | A duplicate versioned OpenAPI route | The framework already serves the document at its own path, and both were proxied | One path | |
| 53 | infra | Two identical connection-string converters and three formats of one checkpoint key | The same transformation written twice; one key built three ways, one of them inline beside a named builder | One of each | |
| 54 | infra | Three copies of "release a counter atomically", one of them not atomic | The idiom duplicated, including a version that loses the race it exists to win | One helper | |

## Documentation

| # | Source | Item | Why removed |
|---|---|---|---|
| 55 | notes | Five root design documents, 5,195 lines | Three of them formed a precedence chain declaring each other superseded **in place**, with no single authority. One described a learning model this redesign deletes. `R0` makes them inputs, not authority |
| 56 | docs | An agent-instruction file containing its own body twice, plus a rewritten copy of its sibling | Both advertised a documentation layout whose files do not exist, and one pointed five distinct rule references at itself |

### `docs/` and `plans/` are kept

Not removed. They are **demoted**, which is a different operation:

| Tree | Status |
|---|---|
| `docs/` (3,510 lines) | Kept. No longer authority — this folder governs where they overlap (`R0`). Documents that contradict the design are corrected or marked historical in place, not deleted |
| `plans/` (51,127 lines of markdown) | Kept. The execution record of how the codebase got here, including plans this redesign supersedes. Superseded plans are **closed**, not erased |

The reason to keep them is the same reason they are not authority: they are a
record of *what was done*, and a record that contradicts the current design is
still evidence about how the code reached its present shape. Deleting 45,000 lines
of untracked history to remove a contradiction resolves the contradiction by
destroying one side of it.

`R0` is satisfied by **precedence, not deletion**: one authority, and everything
else read as input.

## Deliberately absent, never built

Distinct from the table above: these were never in the codebase and are recorded
so a later reader does not add them by reflex. Each is `Q*` in
[decisions.md](./decisions.md).

| Absent | Decision | Note |
|---|---|---|
| Observability stack, metrics endpoint | `Q1` | Three values stay `uncalibrated` as the stated cost |
| Scheduled real-model evaluation | `Q2` | Returns with a secret and a budget cap |
| A story gallery in the gate | `Q3` | — |
| Agent sandbox | `Q6` | The agent executes no code; a container protects against a capability it does not have |
| Long-term agent memory store | `Q7` | The library is the durable record and the learner owns it |
| A third plan tier | `Q8` | A larger credit bucket first |
| Credit reservation ledger | `Q9` | Charge at completion; overshoot is bounded by concurrency |
| Architecture baselines, doc-path linting, staleness gates | `Q11` | Snapshots of a structure a redesign invalidates |
| Staging environment, orchestrator manifests, a second broker | `Q12` | Each has a named seam instead |
| Mobile application | `Q14` | Designed for by `H2`; not built |

## Not removed, though it looks like it

Recorded so the list is not misread. Each is a **capability**, and its reason is in
the linked file.

| Kept | Why |
|---|---|
| FSRS arithmetic, with every published weight index | Pure, tested against reference values. Indices must stay aligned with the reference implementation even where a term is unemitted `B2` |
| The dictionary-library contract as a set of protocols | The implementation is an external package pinned to a commit, and the whole suite substitutes it. Trim unused members; keep the seam `A5` |
| Four separate rate limiters | Each guards a different resource with a different release rule. Only the release *idiom* was duplicated `P11` |
| Four idempotency mechanisms | They key on four identities at four layers — a client answer, a command replay, shared work, a worker projection. Not one concept four times `F7` |
| Advisory locks keyed on the high bits of an identifier | A docstring records the **measured** collision rate of the cheaper alternative `D5` |
| The unhandled-error envelope | The only thing keeping a non-domain exception inside the error shape the client keys on `H14` |
| Two retry schedules of different orders of magnitude | Seconds for durable jobs, sub-millisecond jitter for compare-and-swap. Different failure modes |
| Answer-safety assertions | A per-variant field allowlist. Its failure is **silent**: nothing breaks, assessment just stops meaning anything `C6` |
| The scripted deterministic provider | It is what makes agent-behaviour tests possible at all `N5` |
| Compaction | Mandatory. Nothing else bounds a thread `G12` |
| The migration gate and its head assertion | A healthy database is not a migrated database `O4` |
| The migration-chain test against a fresh database | The suite builds its schema from the models, so nothing else observes what a migration produces — including the delete rules deletion depends on `ops/testing.md` §7 |
| `NO ACTION` foreign keys with hand-ordered deletion | Two schemas, one database, and a cross-schema reference with no constraint. A cascade cannot traverse it, so declaring one is false safety `O11` |
| The coordinated both-schema dump, taken with writes stopped | A schema-selective dump restores to a broken referential state `O10` |
| Workers health-gated before the API on deploy | Jobs are written by the API and consumed by a worker `O4` |
| Parameterised, loopback-bound host ports | A hardcoded port makes the restore rehearsal and the live stack mutually exclusive on one host `ops/devops.md` §1 |
| The edge's non-compression and non-buffering carve-out for assistant SSE | Compression buffers streaming frames `O2` |
| Zero retries and one worker in the golden journey | Quota is a per-learner budget and answering mutates session state. A spec passing only on the second attempt is reporting a real recovery defect `ops/testing.md` §6 |
| The rendered-value wait before an automated contrast scan | The scan reads *rendered* colour; one engine reports an animation finished at a still-transparent value. Measured, not guessed `ops/testing.md` §10 |
| Keyboard operability and visible focus on the study loop | Used hundreds of times by one person. A capability, not a scan `modules/web.md` §9 |
| Signing-secret rotation with an overlap window | Removing it invalidates live tokens on every rotation `H5` |
| A denylist for production and an allowlist for development | The asymmetry is the point: a trailing space silently unset production, and an unrecognised environment name must get development's restrictions without its latitude |

## Measured totals

Only what was measured:

```text
frontend BFF and error plumbing        ~1,334
hand-written DTO mirrors                 ~844
unreferenced registry surface              635
stories and their configuration        ~1,830
browser specs beyond the journey       ~2,300
second CI runner                           307
nightly workflow                           152
release script                             130
meta-tooling scripts + baselines         2,152
root design documents                    5,195
```

Not counted, because they are **kept and demoted** rather than removed: `docs/`
(3,510) and `plans/` (51,127).

Not counted: the learning state machine, the HITL machinery, the agent's inline
execution path, and the migration squash. Each is a **rewrite** rather than a
deletion, so a removed-lines figure would be misleading — the replacement is not
zero lines, it is fewer.
