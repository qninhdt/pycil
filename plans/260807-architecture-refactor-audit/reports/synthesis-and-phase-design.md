# Architecture Refactor — Audit Synthesis & Phase Design

Five audits, ~45k LOC across pycil (api/worker/shared/web) + lexi-ai.
Source reports in this directory. Every claim below carries `path:line`.

---

## 1. Headline: the premise is half wrong

The brief assumed "AI-generated patchwork, inconsistent architecture, missing
boundaries". At macro level that is **not** what the audits found.

Both Python surfaces run a deliberate hexagonal layout. Evidence of intent, not
accident:

- **Real transactional outbox.** `tasks/application/service.py:91-106` writes
  event + outbox row in the same transaction as the state change, fires
  `pg_notify`; worker `LISTEN`s (`main.py:69-76`) with a cron sweep as backstop.
- **Real Protocol-based port** with boundary test + working fakes:
  `ports/lexi.py`, `tests/test_lexi_boundary.py`, `tests/learning/fakes.py:85`.
- **Self-enforcing architecture:** 9 import-linter contracts + guard tests
  (`test_lexi_boundary`, `test_session_scope_allowlist`, `test_route_auth_coverage`,
  `test_middleware_error_contract`, `test_v1_contract`).
- **Error taxonomy codegen'd into the frontend** as `Record<ApiErrorCode,…>`, so
  adding an API error code breaks the web typecheck.
- **11.8k LOC api tests** + 1.5k worker.
- **Strategy done right:** `lexi_ai/questions/engine.py:75,110,133` dispatches
  purely through `REGISTRY`, zero type branching.
- **Session lifecycle as a pure reducer** with `assertNever` exhaustiveness
  (`apps/web/lib/study/session-machine.ts`).

**The real problem is the opposite of the one stated: over-abstraction and
unenforced claims, not missing structure.** lexi-ai's verdict is explicit —
"over-abstracted, not under; primary recommendation is deletion of indirection,
not addition."

Consequence for this plan: **the deliverable is mostly subtraction.** A
pattern-application pass would make this codebase worse.

---

## 2. What is actually broken

### 2.1 One live bug (highest value finding)

`pycil/ports/lexi.py:88` declares `get_entry -> EntryView | None`. The
implementation `lexi_ai/.../entry_repo.py:61` uses `.scalar_one()`, which
**raises** instead of returning `None`. `content/router.py:144-149` only survives
this on a bare `except Exception`. Type-checkers see a contract that is false.

### 2.2 Claims that are not enforced

- **lexi-ai layering is a rulebook that permits its own violations.** All 5
  contracts pass, because none names the loose root modules.
  `domain/asset_identity.py:18,19,25` imports `config`, `constants`, and the
  *private* `normalize._CTRL_RE` at runtime.
  *Correction to the source report:* the `domain/ports.py:44-56` outward imports
  are inside `if TYPE_CHECKING:` — type-only, materially lower severity.
- **`SenseRepo` port lies by 2 methods.** `pending_relations` /
  `apply_resolutions` are declared on the port but live in
  `SenseRelationResolutionMixin`, not `SqlSenseRepo`. Inversely,
  `words.mark_error` is called at `generation_writer.py:91` but absent from the
  `WordRepo` protocol — a working call no type-checker can see.
- **8 function-local imports** dodge import-linter. *Verified correction:*
  `common/errors.py` and `config.py` import nothing from `pycil`, so the local
  imports of them (`content/application/service.py:144,148`,
  `content_facade.py:19`, `generation_quota.py:52`, `persistence.py:86,87`) are
  **cargo-cult, not cycle-dodges** — hoisting them is mechanical. Only
  `hitl.py:121,148` need checking.

### 2.3 Absent transaction boundary

**48 `commit()` sites** (verified by count), top offenders
`tasks/application/service.py` (7), `assistant/application/hitl.py` (7),
`hierarchy/application/service.py` (5), `assistant/router.py` (5).

Commit ownership is negotiated by threading `commit: bool = True` through four
layers (`tools.py:148` → `hierarchy_facade.py:120` →
`hierarchy/application/service.py:59` → `cache.defer_invalidation`), plus a
session-scoped side-channel `session.info["pending_defset_invalidations"]`
(`cache.py:118`) the caller must remember to flush (`tools.py:69`).

Counted precisely: **10 signatures carry the flag** — 4 domain services that
actually branch on it (`hierarchy/application/service.py` `move_node`,
`soft_delete_node`, `set_visibility`; `content/application/service.py`
`remove_sense`), 4 facade methods that only forward it (`hierarchy_facade.py` ×3,
`content_facade.py` ×1), and 2 local `operation` callbacks in `tools.py` that exist
only to receive it. The `False` branch of all four exists solely for the assistant
HITL path.

That is a Unit of Work implemented as a convention — the "boolean flag
controlling too much behavior" smell from the brief, and the single strongest
pattern case in the codebase.

### 2.4 Duplicated non-transactional enqueue

4 identical submit-then-enqueue blocks, each swallowing failure in
`except Exception: pass` — verified at `tools.py:243`, `answering.py:393`,
`content/router.py:112`, `session_flow.py:274`.

The reconcilers that repair these are **correct** design (arq-in-Redis cannot
join a Postgres transaction), but `reconcile_pending_grades` re-enqueues by
*response id, not task id*, which is the sole reason `_converge_task_snapshot`
(`grade_answer.py:59-99`) exists to re-find the task by work key. That is a real
design seam, not patchwork.

### 2.5 Pseudo-port

`ports/centrifugo.py` sits beside a proper port and is not one: module functions,
`httpx` built inline per call, reads global `settings`, no Protocol, no fake.
Consumers import the concrete module (`auth/router.py:20`,
`account_lifecycle/router.py:15`, `realtime/router.py:17`); tests patch
`client.httpx.AsyncClient`. Two philosophies in one directory.

### 2.6 Dead code (~roughly 400 LOC across both repos)

- `session_store.py` (862 LOC): `pass_checkpoint`(695), `open_retry`(742),
  `lock_score`(664), `mark_round_used`(452), `set_exposed`(460),
  `mark_fsrs_applied`(473), `add_excluded`(243) — zero non-test callers,
  superseded by `apply_checkpoint_projection`(483). ~200 LOC.
  *Refining the count in this document:* the 14 figure is **call sites, not tests**.
  Only 2 of them (`test_session_store_cas.py:44,47`) belong to the one test that
  asserts `pass_checkpoint`'s own behavior; the other 12
  (`test_session_recap.py` ×6, `test_session_read.py` ×5, `test_apply_verdict.py`
  ×1) are **fixture setup** arranging a passed count. Those repoint to a helper;
  see §6.2.
- `content/service.py:36,43` `rename_deck`/`delete_deck` — no callers, no tests.
- Zero-importer abstractions: `tasks/domain/schemas.py:10 AsyncTaskSnapshot`
  (wire shape hand-built by `task_snapshot()` at `service.py:75` instead),
  `ports/centrifugo.py:25 sign_subscription_token`, `:66 unsubscribe_channel`.
- `ports/lexi_provider.py` + `ports/lexi_embedded.py`: 5-function chain where 2
  functions exist only to be patched by one test.
- lexi-ai: `constants.py` 515 LOC of which 188 is an ISO-639 table (`:311-497`),
  plus dead `SCORE_KINDS`, `REL_SYMMETRY`. 14 unconsumed public facade methods.
- `hierarchy/router.py:44` executes `reads.TRACKED_SENSE_CEILING = 20_000` at
  import time — a router mutating another module's global, re-asserting a value
  already set at `reads.py:37`, with a comment referencing `_tracked_sense_ids`
  which no longer exists.

### 2.7 Misplaced, not missing

- `learning/application/planning.py:30` and `round_scheduler.py:29` import
  `AdmittedSense`/`SenseProgress` out of `infra/session_store.py`. Pure
  dataclasses that belong in `learning/domain/`.
- lexi-ai `db.py` (root) imports `infrastructure.db.models`, while
  `asset_repo.py:27` / `question_repo.py:24` reach back out for `session_scope`.
  `vectors.py` is 31 lines / 1 function / 1 importer. Both are migration
  leftovers pointing the wrong way.
- `session_store.py` holds 8 unrelated responsibilities (keys, meta, delivery
  bind, round bookkeeping, CAS projections, prepare budget, teardown, two
  unrelated Lua quotas).

### 2.8 Cross-language drift: silent, and no test can catch it

Two contracts are defined in Python and re-declared in TypeScript. Neither has a
test that fails when the Python side moves, because both TS test suites assert
against same-repo literals.

**Grading payload.** `apps/web/lib/realtime/task-snapshot.ts:31-46` validates the
async-task envelope properly (checks `schema === "async-task.v1"` and every
field), then stops at `result: Record<string, unknown>`. The inner grading fields
come from `packages/shared-py/shared/realtime/payloads.py` `GradingResult.to_dict()`
and are read by string key at `lib/study/grade-snapshot.ts:68-74` —
`result?.gradeScore`, `?.isCorrect`, `?.reveal`, `?.masteryBefore`,
`?.masteryAfter`. Every read is defensive (`asNumber`/`asBoolean` → `null` on
mismatch), so renaming `gradeScore` in Python produces **a silently null verdict**:
no exception, no TS error, `tests/unit/task-snapshot.test.ts` still green. The
learner answers and sees a blank score.

**Mastery bands.** Verified literally identical in both languages and mirrored by
hand:

| | Source | Bands |
|---|---|---|
| TS | `apps/web/lib/design/mastery.ts:24-30` | `0-10, 11-30, 31-55, 56-80, 81-100` |
| PY | `apps/api/pycil/policy/policy.py:50-56` | `_Band(0,10) … _Band(81,100)` |

`tests/unit/mastery.test.ts` is thorough about every boundary — against local
literals only, so an API-side edge move passes CI. Both sources render on the
same screens (server `masteryStageName` on deck rows, local `masteryBand()` on
dashboard and study verdict), so drift shows one learner two labels for one
score. The TS file's own comment warns about exactly this and nothing enforces it.

Both assert **semantic agreement across languages**, which survives any redesign
of shapes, tables, or signatures — so both are in scope. The right mechanism is
codegen rather than a test; see §4.1.

### 2.9 Performance, fixable without a pattern

Redis N+1 four times over: `round_scheduler.py:132-136,147-149,163-165,187-192`,
`session_flow.py:463-468`, `session_recap.py:70-74` each re-run `get_admitted`
then one `get_progress` per sense. A single `/next` walks the admitted set 2-4
times. One `load_session_state()` returning `dict[int, (purpose, progress)]`
removes it — **a function, not a pattern.**

### 2.10 Rolling-deploy compatibility for a deploy that never happened

**No audit found this category. It is the purest form of the debt the goal
targets: complexity carried for users and data that do not exist.**

Three job entry points for one operation (`jobs/grade_answer.py`):

| Symbol | Line | Production enqueue sites |
|---|---|---|
| `grade_answer` | 97 | **none** — reached only via `grade_answer_v1` |
| `grade_answer_v1` | 119 | 1, and only from `reconcile_pending_grades.py:94` |
| `grade_answer_task` | 124 | `answering.py:394`, `reconcile_async_tasks.py:28` |

`grade_answer_v1` is a one-line delegation whose docstring states its own reason:
*"Versioned producer target; retain `grade_answer` while old jobs drain."* There
are no old jobs to drain. All three stay registered in `main.py:118-120`, and
three test files pin the legacy names.

The `_converge_task_snapshot` seam (§2.4) exists **solely** because
`reconcile_pending_grades` re-enqueues by response id via the legacy name. Point
that reconciler at `grade_answer_task` with a task id and the seam disappears —
that is the root-cause fix, and it is only reachable by deleting the compat path.

Same pattern elsewhere:

- `generate_word.py:18` — `owner_uid: str | None = None`, optional per its
  docstring so *"a job already queued by the previous release settles instead of
  raising TypeError during a rolling deploy."* Nullable in a signature, forcing an
  `if owner_id is not None` guard, for a queue that is empty.
- `reconcile_async_tasks.py:19-20` — a branch for rows *"written by the previous
  release"* that cannot exist.

### 2.11 Migration history describes a product that was never shipped

25 pycil migrations, 4 lexi-ai. The history contains an expand/validate pair
(`0003`/`0005`), a legacy-label backfill (`0016`: *"Map any legacy label: review
-> scheduled"*), a schema removal (`0009_remove_legacy_product_schema`), a table
added then dropped (`0010`+`0013` → `0025`), and a lifecycle v2 rewrite. Every one
of those steps is ceremony for preserving data that does not exist.

Enabling factor already present: `scripts/rehearse-fresh-schema.sh` plus
`verify-baseline.sh` and `fk-delete-rules-baseline.json` — a squash can be
verified by diffing the resulting schema against the current head, mechanically.

---

## 3. What to keep, explicitly

Recorded so no later phase "tidies" these away:

| Kept | Why |
|---|---|
| Transactional outbox (`tasks`→`realtime`) | Correct, tested, documented |
| `ports/lexi.py` Protocol + fakes | The model the other ports should copy |
| `hierarchy_facade.py` | Real Facade — every method adds `_owned_node` re-authorization for LLM-chosen IDs. Security boundary, not a shim |
| `questions/` Strategy via `REGISTRY` | Textbook, zero branching |
| `render.py` `RenderKind` chains | Legitimate projection layer |
| `VectorIndex` `None` object | Correct and documented (`vectors/__init__.py:25-38`) — do **not** add a Null Object |
| The reconcilers | Compensating reads of committed state; unavoidable given arq/Postgres split |
| Web BFF token sealing | Token never leaves server; `lib/api/request.ts` re-seals on rotation |
| Web session reducer + `assertNever` | Unhandled state = compile error |
| Error taxonomy → frontend codegen | Cross-repo typecheck coupling that works |
| Hand-written `types/learning.ts` | Deliberately corrects two things the OpenAPI doc cannot express |

**Rejected as over-engineering** (agreed across audits): Repository over
SQLModel; Repository over lexi-ai's `UnitOfWork`; event bus over the outbox;
`AppError` subclass hierarchy; DI container; `hierarchy_facade` → class; Strategy
for `render.py`; Null Object for `VectorIndex`.

---

## 4. Spending the pre-production authorization where it pays

Goal: minimum technical debt and maintenance cost, decided now while there are no
users and no production data. That reorders what the authorization is worth.

**Worth using, high value:**

1. **Delete rolling-deploy compat (§2.10).** Retires 2 of 3 grade entry points, a
   nullable parameter, and a reconciler branch. Unlocks the root-cause fix for the
   `_converge_task_snapshot` seam, which is otherwise unreachable. This is the
   single best debt-per-effort item in the audit.
2. **Squash migrations to one baseline (§2.11).** 25 → 1. Removes expand/validate
   pairs, legacy backfills, and a table added-then-dropped. Verifiable
   mechanically against the current head via the existing
   `rehearse-fresh-schema.sh` + `verify-baseline.sh`. Cost of doing this later:
   impossible, once real rows exist.
3. **lexi-ai internal restructuring.** No cross-repo coordination needed.

**Not actually a break at all:** `read_models` → `contracts/dictionary.py`. I
listed this as needing a coordinated two-repo re-pin; verifying it shows pycil
production code never imports `read_models`. See §6.3 — it lands in phase 6 as
internal work.

**Recommend still NOT using: REST contract + facade signature breaks.**

Not caution — there is no defect to fix. The REST surface is guarded by
`test_v1_contract`, consumed by a typed frontend, error codes codegen'd. The one
genuine contract defect is §2.1 `get_entry` nullability, which is a bug fix. A
gratuitous reshape would cascade through 18.9k LOC of `apps/web` and *raise*
maintenance cost, which is the opposite of the goal. Debt is paid by deleting
things, not by renaming working ones.

### 4.1 A better mechanism than tests for the cross-language drift

`scripts/extract-error-codes.py` already solves this exact class of problem:
generate the TS from the Python, CI runs the extractor and fails on a dirty tree
(`.github/workflows/test.yml:72-74`). Its own docstring records that three codes
had silently drifted before it existed.

Both §2.8 drift risks are the same shape and should use the same mechanism rather
than a test asserting local literals (which is why they leave Phase 0 for a phase
of their own):

- **Mastery bands** → generate `lib/design/mastery.ts` bands from `policy.py`
  `LEVEL_PROFILES` + `STAGE_NAMES`. Drift becomes a red build, not two labels on
  one screen.
- **Grading payload** → generate the inner-result validator from
  `shared/realtime/payloads.py` `GradingResult`, so `grade-snapshot.ts` stops
  reading by defensive string key.

Codegen'd contract beats a test here: a test asserts *what the fixture says*,
codegen asserts *what the other language says*. This is a structural fix, and it
is why these move out of Phase 0 into their own phase.

**Still blocked:** codegen for `lib/api/types/*`. The OpenAPI document has two
known inaccuracies hand-corrected at `types/learning.ts:1-15`. Fix the document
first, or codegen enshrines the lies.

---

## 5. Phase design

Ordering principle: **delete before restructure** (shrinks every later phase),
**make guards honest before trusting them**, **behavioral net before touching
scheduling math**.

Prerequisite, not a phase: **commit the 41 dirty files.** The working tree is
currently mid-migration — `tests/jobs/test_word_generation_jobs.py` is deleted and
its replacement `tests/content/test_word_search_auth_boundary.py` is untracked, so
the suite is momentarily weaker than either state. Refactoring on top of that makes
regressions unattributable.

| # | Phase | Scope | Risk | Why here |
|---|---|---|---|---|
| 0 | Behavioral safety net | FSRS interval/mastery, grading correctness, session progression, task/outbox idempotency | Low | Only tests that survive a redesign. Excludes REST shape / facade signature / DB column tests by design |
| 1 | Deletion sweep | §2.6 dead code, both repos; **§2.10 rolling-deploy compat** (2 of 3 grade entry points, `owner_uid` nullability, `reconcile_async_tasks` legacy branch). Repoint the 12 `pass_checkpoint` setup call sites onto a fixture helper (§6.2) | Low | Shrinks phases 5-9. Best debt-per-effort in the audit, and unblocks phase 9's root-cause fix |
| 2 | Make guards honest | import-linter contracts name lexi-ai root modules; hoist cargo-cult local imports; extend router-only test to `learning`/`content`; delete `hierarchy/router.py:44` | Low | Later phases rely on these gates. Turns §2.2 into true-or-visibly-false |
| 3 | Fix the lying contracts | `get_entry` nullability (§2.1); `SenseRepo` port ±2 methods; `words.mark_error` onto `WordRepo`; move `lexi_ai.contracts` imports out of `learning/domain` | Low-Med | Real bug + type-checker blindness + one layering violation |
| 4 | Cross-language codegen | Generate mastery bands and the grading-result validator from Python (§4.1), on the `extract-error-codes.py` pattern + CI dirty-tree gate | Low-Med | Structural fix for §2.8. Independent of everything else |
| 5 | Migration squash | 25 → 1 baseline (§2.11), verified by diffing the rehearsed schema against the current head | Med | Only possible while there are no rows. Do it after 1 so dropped tables never enter the baseline |
| 6 | lexi-ai internal tidy | `db.py`/`vectors.py` under `infrastructure/`; split `constants.py`; collapse unconsumed facade methods | Med | Internal only, no pycil coordination |
| 7 | `learning` module | Split `session_store.py` 8-ways; move `AdmittedSense`/`SenseProgress` to domain; kill Redis N+1 (§2.9) | Med-High | Largest file, touches scheduling — needs phase 0 |
| 8 | Transaction boundary | UoW; retire `commit: bool`; retire `session.info` side-channel | High | The one strong pattern case. Needs 1-2 done first |
| 9 | Task dispatch | `TaskDispatcher` collapsing 4 enqueue blocks; point `reconcile_pending_grades` at `grade_answer_task` by task id, retire `_converge_task_snapshot` | Med-High | Depends on 8. The seam only becomes removable once phase 1 deletes the legacy alias |
| 10 | Centrifugo real port | Protocol + fake, mirroring `ports/lexi.py` | Low-Med | Independent; can run parallel to 7-9 |

Each phase merges to `main` green. Phases 3, 4 and 10 are independently shippable
if you want early wins.

**Deliberately not in scope:** REST contract redesign, lexi-ai facade signature
changes, `apps/web` restructuring (audit found it coherent), any new pattern in
`questions/`, `render.py`, or the outbox.

---

## 6. Questions resolved by reading the code

Three items were listed here as needing a product decision. All three are answered
by source; recorded with verification so no later phase re-opens them.

### 6.1 HITL transaction ownership — UoW is justified, requirement is real

`_run_sensitive` (`tools.py:35-67`) commits the domain write **and** the action
outcome in one transaction: `operation(session, False)` writes the node change,
then the same block sets `action.status = SUCCEEDED`, writes the audit row, and
calls `session.commit()` once (`:51-62`).

That atomicity is load-bearing. Split it and a crash between the two commits
either re-runs an already-applied tool (action still `EXECUTING`, node already
moved) or loses the result the SSE resume path reads back. So HITL **cannot** own
a separate transaction — the flag does not simply delete.

The deferred-invalidation side-channel is equally real, and `cache.py:121-133`
records the bug that produced it: a mutation that does not commit cannot delete
its own Redis keys, because the delete must follow the commit or a concurrent
reader repopulates from the pre-commit generation. Skipping the record *"left the
assistant's approved mutations with a stale definition set cached for the full hour
of `_TTL`"*.

Conclusion: a genuine requirement expressed in the wrong shape — `commit: bool`
across 4 layers, 6 two-branch tails, plus an untyped `session.info` dict the caller
must remember to flush. A UoW that owns the commit and runs registered post-commit
hooks keeps both guarantees and makes the services unconditional. **Phase 8 is
unblocked; no user decision needed.**

### 6.2 `pass_checkpoint` — delete it, no coverage lost

Earlier count in this document was wrong. Actual: **11 call sites, of which exactly
one asserts `pass_checkpoint`'s own behavior** (`test_session_store_cas.py:42`).
The other 10 (`test_session_recap.py` ×6, `test_session_read.py` ×5 minus overlap,
`test_apply_verdict.py:70`) call it as **fixture setup** to arrange a passed count.

`apply_checkpoint_projection(state_action="complete")` (`session_store.py:483`) is
a strict superset: same `passed` increment, same `open_*` clearing, same
`retries_used` reset, same terminal-at-N — plus replay dedup via the `projected`
set, plus `score`/`fsrs_applied`. Its behavior is already covered by
`test_checkpoint_projection_is_atomic_and_idempotent` and
`test_checkpoint_projection_deduplicates_interleaved_replay`.

Action: delete `pass_checkpoint` and its one behavioral test; repoint the 10 setup
sites at a conftest helper wrapping `apply_checkpoint_projection` with a fresh
`uuid4`. Mechanical. **No behavior question for the user.**

### 6.3 `read_models` → `contracts/dictionary.py` — internal, not cross-repo

Earlier claim in §4 was wrong: this is **not** a coordinated two-repo re-pin.

pycil production code imports `read_models` **zero** times — only
`lexi_ai.contracts` and `lexi_ai.Lexicon`. The sole pycil touchpoint is two lines
in one test (`tests/content/test_lexi_contract_parity.py:176,193`), and that test
imports the *installed* dataclass on purpose, to catch a manifest pinned without a
synced venv. It just changes import path.

Inside lexi-ai there are ~28 internal importers — a mechanical repoint.

It also closes a half-done migration the code itself documents:
`contracts/__init__.py:10-12` states the DTOs *"migrate into `contracts/dictionary.py`
in Phase 3, when the `read_models` importers are repointed"*, and
`read_models.py:1` is titled *"Public read models for the lazy lookup API (Phase
6)"*. Those plan references in code violate the repo's own naming rule and stop
being resolvable once the plan is renumbered — completing the move deletes them.

**Do it in phase 6.**

---

## 7. Still open

1. **Is the assistant's direct `get_lexi_client()` deliberate?**
   (`tools.py:179`, `content_facade.py:37` bypass `Depends`, so
   `dependency_overrides` cannot reach them.) If deliberate, document it; if not,
   phase 2 fixes it.
2. **Redis/arq provider module** mirroring `lexi_provider` — worth it, or is
   monkeypatching `_redis` in tests acceptable?
