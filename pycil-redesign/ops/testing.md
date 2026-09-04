# ops/testing

Three scopes, a named invariant checklist, and one deterministic provider.
Decisions `N1`–`N5`, `N11`.

## 1. The problem being corrected

Measured: the API has 13,749 test lines against 12,170 production lines; the worker
1,637 against 916. Test code is roughly equal to production code and, in the
worker, nearly double.

That is not thorough testing. It is a verification program.

But cutting to a handful of contracts is the opposite error and violates `R4`. The
answer is neither a count nor a coverage percentage: it is a **named invariant
checklist** (`N1`).

Each module and cross-cutting file in this folder ends with its invariants. **Each
line must have a named test. A line without one is the gap.** That is checkable in
a way a percentage is not — and unlike a percentage, it cannot be satisfied by
testing something easy.

## 2. Shape

```text
SCOPE
unit          no external dependency, in-process
integration   real Postgres and Redis via containers                     (N2)
e2e           the full stack, ONE golden journey                          (N2)

PURPOSE — cuts across scope
contract      an assertion. Deterministic. Always runs in the gate
measurement   a number. Never gates                                      (N4)
```

The assertion/measurement split is the distinction worth keeping. A measurement
varies between identical runs, so gating on it makes the gate a coin flip. It
belongs as a recorded number and a reason to investigate — not a red build.

## 3. Fail closed

```text
a test that cannot reach its dependency FAILS
it never skips
```

`N3`. A skipped test reporting green is worse than a failing one, because it looks
like coverage.

Containers are what make this practical: the test brings up its own dependency, so
"unreachable" means a real fault rather than a forgotten setup step `[R33]`. It
also means a clean clone runs the integration suite with no prior local setup.

The corollary is a rule about the previous state of this repository: a suite that
announces "credential not configured — skipping" and reports success has been
green while proving nothing. Under `N3` that outcome is a failure.

## 4. The scripted provider

`N5`. A deterministic model endpoint, kept.

It exercises the **real** client, the real streaming parser, the real tool dispatch,
and the real policy path — with only the model's choices fixed. Without it every
agent-behaviour test is billable, non-deterministic, or both, and agent behaviour is
where the product's hardest logic lives.

Scenario selection is by a marker the test controls in the request, because that is
the only input a browser-driven test can influence.

What it makes testable, none of which is reachable otherwise:

```text
a tool call that requires approval, approved and rejected
truncation mid-tool-call
a content refusal treated as a result
compaction triggering, without splitting a tool call from its result
an injection payload in a tool result failing to steer a destructive call
```

## 5. Integration: what needs a real dependency

Not everything. A real dependency is needed exactly where the behaviour **is** the
dependency's behaviour:

| Needs real Postgres | Why |
|---|---|
| Claim under concurrency (`SKIP LOCKED`) | The primitive is the point |
| Fence rejection of a stale write | Ordering under contention |
| A unique index preventing a double effect | The constraint is the mechanism |
| Delete rules and hand-ordered deletion | See §7 |
| The migration chain applying to head | An ORM-built schema proves nothing about it |
| Recursive readability and top-K selection | The query *is* the logic |

| Needs real Redis | Why |
|---|---|
| Broker claim, acknowledgement, reclaim after a timeout | Stream semantics |
| A counter released atomically | The script is the mechanism |
| Session state surviving a reconnect | Expiry behaviour |

Everything else is a unit test. FSRS arithmetic, the depth ladder, the sampling
table, session-length derivation, the credit balance calculation, error mapping —
all pure, all fast, none of them needing a container.

## 6. The golden journey

One end-to-end path (`N2`), in the gate:

```text
sign in
  → create a folder, then a deck inside it
  → add a word: request generation, receive the job frame
  → study: exposure, a graded item, a wrong answer, its ungraded re-ask,
    a break, a free-text answer returning a receipt
  → recap, with one answer still being graded
  → open the agent, rename the deck, approve a proposed deletion
```

One journey, proven end to end. It touches every subsystem once: auth, hierarchy,
content, the job substrate, realtime, learning's two axes, the agent, and approval.

Thirteen separate browser specs are not thirteen times the confidence. They are
thirteen times the maintenance, and the previous ones had not executed at all.

Three properties the journey needs, each learned rather than assumed:

**No retries, one worker, no parallelism.** Not a flakiness concession. Quota is a
per-learner budget, generation slots are per learner, and answering mutates session
state — so a quota test running beside the study loop drains the budget the other
depends on, and the failure lands in whichever lost the race. Zero retries is
deliberate: these paths are meant to converge, and a spec that only passes on the
second attempt is reporting a real recovery defect.

**A learner per journey.** Scheduling state is keyed `(learner, sense)`, so a shared
learner makes runs order-dependent: the first passes and the rest find nothing due,
which reads exactly like a planner bug.

**A documented state-setting escape hatch.** No endpoint sets a review date or a
strength value **by design**, so without direct state setting the higher depth
levels are unreachable in a test. The exception is narrow and belongs to the
fixture, not to the API.

## 7. Two tests that are easy to skip and must not be

**The migration chain applied to a fresh database.** The test suite builds its
schema from the models, so **no test observes what a migration actually produces**.
Delete rules, constraint names, and index definitions can differ between the models
and the chain with nothing noticing. One test upgrades an empty database to head and
asserts a single un-branched head — derived, never a hardcoded revision.

This is also what makes the `NO ACTION` decision (`O11`) verifiable: hand-ordered
deletion depends on a forgotten table **aborting** the delete. That property lives
in the migrated schema, so only a migrated schema can prove it.

**Two workers on one queue.** At one worker the double-execution path never runs, so
without this test single-writer is a claim rather than a property — and it would be
discovered in production at the moment a second worker was added.

## 8. Ratio

No target number. But if test lines exceed production lines again, that is a
**signal to review**, not an achievement.

Coverage percentage is not a goal either. The checklist is the goal.

## 9. What is cut

| Cut | Reason |
|---|---|
| Architecture-enforcement contracts, module-cycle baselines | A baseline is a snapshot of the current structure; a redesign changes the structure, so it is wrong from the first commit |
| Documentation path linting | It covered a fraction of the documents and could not validate a forward-looking one at all — its own single failure was a citation of a deliberately untracked file |
| Generated-artefact staleness gates | Two generators for one contract is the defect; one generator removes the need to detect divergence |
| Test-count floors | Their premise is falsified by measurement: no runner here reports zero tests with a success exit code |
| Coverage floors | `N9`. Also declared twice — in the workflow and in a second script nothing executed |
| A story gallery in the gate (`N11`) | It asserted nothing: no runner installed, its accessibility check set to report-not-fail, no story carrying an assertion |
| A design-system lint | Its own header listed what it could not catch. A green gate reading as "the design system holds" is the failure mode |
| Config-file substring assertions | A test that greps a deployment file is a lint on a file outside its scope, and it breaks on reformatting |
| Meta-tests | Tests about tests |
| Real-model tests in the gate | Cost, latency, non-determinism (`N4`) |
| Load tests in the gate | A measurement, not an assertion |
| Browser matrix in the gate | One browser for one journey. Cross-browser rendering is a manual review, and its real findings are recorded in §11 |

## 10. Accessibility

Not a gate, and not absent.

The study loop is used hundreds of times by one person, so keyboard operability and
visible focus are **capabilities** (`modules/web.md` §9), on the checklist. An
automated scan of the whole application every commit is a different thing, and it
was the least reliable job in the previous suite.

One measured finding is recorded here because it will otherwise be rediscovered
expensively: **an automated contrast check reads *rendered* colour**, so a scan that
runs before animations settle reports dozens of violations against a palette that
passes when opaque. Waiting on the animation state is insufficient — one engine
reports an animation finished at a still-transparent opacity. Waiting on the
rendered value is what works, and infinite animations must be excluded or the wait
never returns.

That knowledge is worth more than the job that produced it.

## 11. Manual, deliberately

| What | When |
|---|---|
| A load scenario | Once, to make a capacity claim defensible: one worker then three, concurrent sessions, kill a worker mid-run, show recovery without a duplicate effect. Report the host specification with the latencies, error rate, and recovery time |
| Cross-browser rendering of the study loop | Before a release. Viewport-relative height, safe-area insets, and sticky-footer behaviour are mobile-browser problems first, and the narrow viewport is the only place a missing minimum-width surfaces |
| A rubric-grading sample | Ongoing. This is the measurement `P12` and `B6` are waiting for |
| Screenshot capture at two viewports in both themes | On demand. Evidence for human review, no image comparison — correct for a design system this young |

## 12. Local parity

```text
one command per gate step, and the gate runs those commands
```

`N7`. A step that exists only in CI is a step nobody can debug. Containers are what
make this hold: the integration suite brings up its own dependencies, so a clean
clone runs it.

## 13. The checklist

The invariants are **not** duplicated here. They live at the end of the file that
owns the behaviour:

| File | Invariants |
|---|---|
| [../modules/learning.md](../modules/learning.md) §12 | the two axes, re-ask, session shape |
| [../modules/assistant.md](../modules/assistant.md) §12 | run lifecycle, single-writer, approval |
| [../modules/hierarchy.md](../modules/hierarchy.md) §9 | readability, generation, top-K |
| [../modules/content.md](../modules/content.md) §9 | supply, answer safety |
| [../modules/account.md](../modules/account.md) §9 | identity, credit, export, deletion |
| [../modules/web.md](../modules/web.md) §10 | client obligations |
| [../cross-cutting/auth.md](../cross-cutting/auth.md) §12 | tokens, refresh, CSRF |
| [../cross-cutting/delivery.md](../cross-cutting/delivery.md) §7 | SSE, polling, disconnect, reload |
| [../cross-cutting/messaging.md](../cross-cutting/messaging.md) §11 | job identity, idempotency, work keys |
| [../cross-cutting/security.md](../cross-cutting/security.md) §10 | answer key, wrapping, boundaries |
| [devops.md](./devops.md) §13 | boot, migration, health, drain, restore |

Keeping them beside the behaviour is deliberate: a checklist in one file drifts from
the design, and a checklist inside the design cannot.
