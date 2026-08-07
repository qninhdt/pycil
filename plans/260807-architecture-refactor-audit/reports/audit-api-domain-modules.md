# Architecture audit — `learning` / `content` / `hierarchy` (apps/api/pycil)

Read-only audit. All paths relative to `/home/qninh/projects/pycil/apps/api/`.
Line counts measured with `wc -l`. Reference counts measured with ripgrep over `apps/` split into src-only vs tests-only, excluding definition lines.

LOC baseline (audited scope, 6477 total):

| file | LOC |
|---|---|
| `pycil/learning/infra/session_store.py` | 862 |
| `pycil/learning/application/session_flow.py` | 504 |
| `pycil/learning/application/service.py` | 463 |
| `pycil/learning/application/answering.py` | 406 |
| `pycil/hierarchy/router.py` | 312 |
| `pycil/hierarchy/application/stats.py` | 299 |
| `pycil/learning/router.py` | 287 |
| `pycil/content/router.py` | 271 |
| `pycil/learning/domain/schemas.py` | 235 |
| `pycil/hierarchy/application/service.py` | 224 |
| `pycil/hierarchy/application/reads.py` | 220 |
| `pycil/learning/infra/models.py` | 219 |
| `pycil/learning/application/planning.py` | 209 |

---

## 1. Layering reality check

Declared contract is in the package docstrings: `domain/` = "no session, no HTTP, no ORM"; `application/` = "needs a session but is not a route"; `infra/` = "only layer permitted to define a SQLModel table or talk to Redis" (`pycil/hierarchy/domain/__init__.py`, `pycil/hierarchy/infra/__init__.py`, `pycil/content/*/__init__.py`, `pycil/learning/*/__init__.py`).

### Holds

- **No `domain -> infra` import anywhere in the three modules.** `pycil/hierarchy/domain/schemas.py:8` imports `domain/vocabulary`, not `infra/models`. `pycil/hierarchy/infra/models.py:19` imports the enums *from* domain — correct direction, and the docstring at `:16-19` states why.
- **`application -> SQLAlchemy` is intended, not a violation.** Every application module takes `AsyncSession` as a parameter (`hierarchy/application/service.py:7`, `content/application/service.py:10`, `learning/application/service.py:33`). The `application/__init__.py` docstrings define the layer as session-aware. Not a finding.
- **No router commits.** `grep 'session.commit' pycil/*/router.py` → 0 hits. Commits live in application: learning 6, content 3, hierarchy 5.
- **`learning/domain/` is genuinely pure.** `resolver.py:10` imports `pycil.ports.lexi` (a port, not infra); `grading.py`, `fsrs_wrapper.py`, `schemas.py` import nothing from `infra/`.

### Real violations

**V1 — `application` depends on value types defined in `infra`.**
`learning/application/round_scheduler.py:29` `from pycil.learning.infra.session_store import SenseProgress`
`learning/application/planning.py:30` `from pycil.learning.infra.session_store import AdmittedSense`
Both are plain frozen/mutable dataclasses (`session_store.py:56`, `session_store.py:63`) with zero Redis dependency. `planning.py` is documented as "DB-read + pure" (`planning.py:11`) yet imports a Redis module to name its own output type. `round_scheduler.eligible_requirement` is documented as "Pure over Redis-loaded progress so it is directly unit-testable" (`round_scheduler.py:61`) — the pure function is typed by an infra module. Right home for both is `learning/domain/`. Same class of fix `hierarchy` already applied for its enums (`hierarchy/domain/vocabulary.py:1-11` explains the exact reasoning).

**V2 — `infra` contains domain rules.**
`session_store.py:29` imports `MAX_RETRIES_PER_CHECKPOINT, REQUIRED_CHECKPOINTS` from `pycil.policy.policy`, and three functions *decide terminality* with them:
- `apply_checkpoint_projection` `session_store.py:524-525` (`passed >= required_checkpoints -> terminal="completed"`) and `:533-534` (`retries_used > max_retries -> "retries_exhausted"`)
- `pass_checkpoint` `session_store.py:725-727`
- `open_retry` `session_store.py:773-775`

The same two rules are also computed in `application/service.py:136` (`completes = ... passed_after >= REQUIRED_CHECKPOINTS`) and `:138-142` (`retry_exhausted`). So the completion rule is stated twice, once in each layer, and the infra copy is the one that writes it. Mitigation: two of the three infra sites are dead (see §3), so the practical duplication is `service.py:136-142` vs `session_store.py:524-534`.

**V3 — router mutating another module's constant, redundantly.**
`hierarchy/router.py:44` `reads.TRACKED_SENSE_CEILING = 20_000` while `hierarchy/application/reads.py:37` already defines `TRACKED_SENSE_CEILING = 20_000`. The 5-line justifying comment is duplicated verbatim at `router.py:39-43` and `reads.py:32-36`. It is a no-op at best; at worst it silently defeats any future change to the value in `reads.py`. Note `tests/hierarchy/test_global_analytics.py:271` monkeypatches `reads.TRACKED_SENSE_CEILING`, so the test patches the module the router then overwrites at import time only (import happens once, before the patch — so the test is unaffected today, but the coupling is accidental).

**V4 — business orchestration inside `content/router.py`.**
`content/router.py:74-119` `request_word` performs: quota reservation (`:82`), a compensating release on failure (`:104`), a second release on the join path (`:107`), durable task submission (`:90-102`), and best-effort ARQ enqueue with a swallowed exception (`:110-116`). That is exactly the policy `learning` extracted into `session_flow.request_supply` (`session_flow.py:201-282`) and explicitly documented as "one policy, stated once" (`session_flow.py:8-11`). `content` has no equivalent application function; `hierarchy` has none either but needs none.

**V5 — authorization composed in the router (`content`).**
`content/router.py:219-222` calls `service.deck_ids_for_sense` then `subtree.readable_deck_ids` and raises the 404. The unauthorized read is explicitly flagged as caller-must-narrow (`content/application/service.py:117-120`), so the safety-critical composition lives in the router. `hierarchy` does the same composition *inside* application (`hierarchy/application/viewer_stats.py:13-21`: `session.get` -> `can_read_node` -> `cached_sense_ids` -> `stats.folder_stats`), which is why the assistant can reuse it (`assistant/application/tools.py:20`). The content path is not reusable by anything but HTTP.

**V6 — DTO projection defined in routers.**
`content/router.py:47-71` `_sense_content` and `:230-271` `_sense_detail` are module-level private mapping helpers in a router. `hierarchy` forbids exactly this pattern with a mechanical test (`tests/hierarchy/test_router_is_routes_only.py`, `test_the_router_defines_no_private_helpers`), which applies to `hierarchy/router.py` only.

### Harmless / not violations

- `learning/router.py:229-237` isinstance-dispatch over `session_flow.Delivered | RoundBreak | NoQuestionYet`. This is wire mapping over a closed union the application deliberately returns as data (`session_flow.py:13-15`). Correct as written.
- `content/router.py:133` `del user` and `hierarchy/router.py:246` `del bucket` — deliberate "presence is the contract" markers, documented at `content/router.py:126-131`. Leave.
- `pycil/policy/sense_state.py` holding `UserSenseStats` read by all three modules: documented cycle break (`sense_state.py:1-30`). Correct.
- Function-local imports: `content/application/service.py:144`, `:148` (`NotFoundError`, `ConflictError` inside `_require_live_deck`) and `content/application/generation_quota.py:52` (`pycil.config` inside `reserve_quota`). No cycle exists for any of the three — `common.errors` and `config` import nothing from `content`. These are leftovers, not cycle guards. `hierarchy` bans them in its router (`test_the_router_has_no_function_local_imports`); nothing bans them in `content/application`.

---

## 2. Consistency across the three modules

| concern | learning | content | hierarchy | best |
|---|---|---|---|---|
| repository access | module functions taking `AsyncSession`; raw `text()` (`session_queue.py:21`) + ORM `select()` (`dashboard.py:67`) | module functions; ORM `select()`/`delete()` (`service.py:52,72,86`) | module functions; raw `text()` throughout `stats.py` (`:52,97,128,161,212,265,278`), ORM `select()` in `reads.py`/`cache.py` | tie — same shape everywhere; no repository abstraction in any of them (good, see §5 "leave it simple") |
| SQL style | mixed | ORM only | mixed, split by file | **content** is most uniform; `hierarchy/stats.py` raw SQL is *justified* at `stats.py:4-5` (VALUES/ANY plans) so the split is intentional, not drift |
| transaction boundary | commits inside application, no `commit:` flag | `commit: bool = True` on `remove_sense` (`service.py:68`) | `commit: bool = True` on `move_node` (`:59`), `soft_delete_node` (`:84`), `set_visibility` (`:107`) | **hierarchy** — it also owns the deferred-invalidation mechanism the flag needs (`cache.py:121-146`). But 4 copies of the two-branch epilogue is the top refactor candidate (§4/§5) |
| error mapping | 10 distinct codes, `AppError` subclasses only | 4 codes | 11 codes; single `node_not_found` for unknown *and* unreadable (`access.py:33,41`) | **hierarchy** — deliberate existence-non-disclosure, mirrored by `content/router.py:222` and `session_flow.py:295`. All three raise only `pycil.common.errors` types; `AppError.__init__` derives the wire `code` from the snake_case message, so no module needs its own mapping table. Genuinely consistent. |
| DTO/schema conversion | inline in router (`router.py:96-113`, `155-199`, `269-287`) **plus** `application/question_delivery.ready_question` (`:75-105`) | in router private helpers (`:47`, `:230`) | in `application/reads.py` (`history_read:145`, `hydrate_weakest:99`) **plus** `NodeRead.model_validate` in router (`:71,98,112,126,143,164`) | **learning's `question_delivery`** — the mapping lives next to the answer-safety rule that must not leak (`question_delivery.py:3-7`). Worst is **content**, where projection is unreachable from anything but HTTP |
| authorization | delegates to `hierarchy.require_node_access` (`session_flow.py:179,296`) | delegates (`router.py:169,181,193`) + `subtree.readable_deck_ids` (`router.py:221`) | owns it: `access.require_node_access` (`access.py:18`) + SQL mirror `_READABLE_DECKS_SQL` (`subtree.py:50-83`) | **hierarchy** — one Python gate, one documented SQL mirror, and `tests/hierarchy/test_readability_rule_parity.py` pinning the two together. Two implementations of one rule is normally a smell; here the SQL form is required (set-at-a-time over a candidate list) and the parity test makes it safe |
| caching | Redis is the primary ephemeral store, not a cache | none | generation-fenced L1 (`cache.py`), single entry point `subtree.cached_sense_ids` (`:153-191`) | **hierarchy** — `cached_sense_ids:157-163` documents that it replaced two byte-identical 22-line copies. Failures swallowed on both read and write (`:177-189`) with the "Redis is an accelerator" rationale |
| pagination | none | none | 2 incompatible styles: keyset cursor (`reads.py:192-220`) and Python-side offset slicing of an already-materialized list (`router.py:217-223`) | **hierarchy keyset** (`reads.py:205-208` explains `limit + 1` instead of a COUNT). The `folder_items` offset path slices `cached_sense_ids(...)[offset:offset+limit]` — the full sense set is loaded regardless of page, so paging saves nothing but the `get_senses` call |
| redis acquisition | passed as a parameter (`session_flow.py:99`, `answering.py:30`, `service.py:28`) | parameter (`generation_quota.py:13`) but router pulls the global (`router.py:81`) | global `get_redis()` inside application (`cache.py:30,42,104`) | **learning/content parameter style** — testable without patching a module global |

Net: the three are recognizably one pattern for *authorization, error mapping and service-function shape*, and three different patterns for *DTO placement, pagination and redis acquisition*.

---

## 3. God files / responsibility sprawl (>250 LOC)

### `learning/infra/session_store.py` — 862 LOC, 8 responsibilities

| lines | responsibility |
|---|---|
| 44-78 | value dataclasses (`SessionMeta`, `AdmittedSense`, `SenseProgress`) |
| 84-105 | key builders + `_opt_int` |
| 111-246 | creation and plain reads (`create`, `get_meta`, `get_admitted`, `get_progress`, `excluded_ids`, `add_excluded`) |
| 252-399 | consume-once delivery bind (`get_delivered`, `set_delivered`, `consume_delivered`, `restore_delivered`, `reopen_bound_delivery`) |
| 405-477 | round bookkeeping + flag setters (`current_round`, `advance_round`, `mark_round_used`, `set_exposed`, `set_awaiting_grade`, `mark_fsrs_applied`) |
| 483-787 | CAS mutations (`apply_checkpoint_projection`, `reserve_round_delivery`, `claim_prepare_attempt`, `lock_score`, `pass_checkpoint`, `open_retry`) |
| 793-802 | teardown (`end_session`) |
| 808-862 | per-learner rate slots: 2 Lua scripts + `_take_slot`, `take_generation_slot`, `take_grading_slot`, `release_grading_slot` |

**Finding S1 — ~21% of this file is unreachable from production code.** src-only ripgrep, definition lines excluded:

| function | src refs | test refs | superseded by |
|---|---|---|---|
| `pass_checkpoint` (`:695-739`) | **0** | 14 | `apply_checkpoint_projection:514-525` |
| `open_retry` (`:742-787`) | **0** (3 hits are the *string* `"open_retry"` at `service.py:68,132,140`) | 5 | `apply_checkpoint_projection:526-534` |
| `lock_score` (`:664-692`) | **0** (1 hit is a docstring at `service.py:14`) | 2 | `apply_checkpoint_projection:535-536` |
| `set_exposed` (`:460-463`) | **0** | 6 | `reserve_round_delivery:589-590` |
| `add_excluded` (`:243-246`) | **0** | 2 | `reserve_round_delivery:596-598` |
| `mark_round_used` (`:452-457`) | **0** | 0 | `reserve_round_delivery:588,595` |
| `mark_fsrs_applied` (`:473-477`) | **0** | 0 | `apply_checkpoint_projection:537-538` |

Roughly 180 LOC, six of seven kept alive only by tests. `mark_round_used` and `mark_fsrs_applied` have no reference at all. Each carries a full WATCH/MULTI CAS loop with its own backoff comment, so they are not trivial dead weight — they are seven more copies of the retry idiom a reader must diff against the live one. Two of the three §1-V2 domain-rule-in-infra sites are inside this dead set.

**Proposed split** (after deleting S1), target names kebab-case per project convention:

- `session-state-keys.py` — dataclasses + key builders + `_opt_int` (~65 LOC). Note: the dataclasses should go to `learning/domain/` instead, per §1-V1.
- `session-lifecycle-store.py` — `create`, `get_meta`, `get_admitted`, `get_progress`, `excluded_ids`, `end_session` (~180 LOC)
- `session-delivery-bind-store.py` — the consume-once block `:252-399` + `reserve_round_delivery` (~200 LOC). These five functions share `current_qid` and are the only writers of it; splitting them apart would be the arbitrary cut.
- `session-checkpoint-projection-store.py` — `apply_checkpoint_projection`, `set_awaiting_grade`, `advance_round`, `current_round` (~130 LOC)
- `learner-rate-slots.py` — the whole `:805-862` block, **moved out of `learning/infra` entirely**. It shares no key namespace and no dataclass with sessions (`session:generation-quota:{owner}`, `session:grading-quota:{owner}` are per-learner, not per-session), and `take_generation_slot` is consumed by `session_flow.py:246` while `take_grading_slot`/`release_grading_slot` are consumed by `answering.py:331,372`. Cleanest cut in the file. `content/application/generation_quota.py` is the same concern for a different budget and is already its own 83-LOC module — the precedent exists.

### `learning/application/session_flow.py` — 504 LOC

Contents: `start` + `_plan_under_stable_scope` (`:97-185`), `SupplyRequest` + `request_supply` (`:188-282`), `authorize` (`:285-299`), `next_question` + `_try_deliver` (`:302-418`), `read_live` + its 2 view dataclasses (`:421-504`).

**Is the session_flow / service / answering / planning / round_scheduler split coherent?** Mostly yes, with two arbitrary edges:

Coherent:
- `planning.py` — pre-session, DB-read + pure, produces `(admitted, demands)`. Clean input/output boundary (`planning.py:194-209`).
- `round_scheduler.py` — decides *which* requirement, pure core (`eligible_requirement:51-120`) + 4 Redis-scanning predicates. Clean.
- `service.py` — the FSRS apply engine. Documented as the correctness core with a Postgres-authoritative idempotency argument (`service.py:9-20`). Genuinely one state machine; do not split.
- `answering.py` — the compensation matrix. Its own docstring (`:8-19`) explains the decomposition by branch (`_bind` / `_apply_now` / `_defer`) rather than by line count. Correct.

Arbitrary:
- **`read_live` (`session_flow.py:447-504`) does not belong in `session_flow`.** It is documented as "A TRUE read: it advances nothing and reserves nothing... the counter-example to `next_question`" (`:452-453`). It shares no helper with `start`/`next_question`/`request_supply` and its two dataclasses (`SenseProgressView:421`, `LiveSessionView:434`) are used nowhere else. Target: `session-read-model.py`, beside `session_recap.py` which already serves the completed-session half of the same route (`router.py:151,185`). That would put both branches of `GET /sessions/{id}` in one place.
- **`request_supply` (`:201-282`) is not session *flow*, it is supply admission.** It is called from `start:137` and `next_question:344`, and its 40-line docstring is entirely about two independent bounds and a task-registry contract. Target: `question-supply-request.py`. Leaves `session_flow` as `start` + `authorize` + `next_question`, ~250 LOC — one coherent "advance the session" machine.

After both moves `session_flow` is ~250 LOC and each of the three extracted concerns is independently testable.

### `learning/application/service.py` — 463 LOC
`apply_checkpoint_result` alone is 214 LOC (`:73-286`) covering: fallback/retry classification (`:97-147`), FSRS apply under a claim (`:149-226`), terminal `Response` mutation + commit (`:228-241`), and best-effort Redis projection with a 3-attempt retry loop (`:243-270`). The classification block (`:131-147`) is pure over values already in hand and is the piece duplicated against `session_store.py:524-534` — extracting it to `learning/domain/` as `classify_checkpoint(...)` would fix §1-V2 and cut 20 LOC of the giant function. The rest is one transaction and should stay whole (`application/__init__.py` explicitly lists `service.py` as must-not-split).

### `learning/application/answering.py` — 406 LOC
Leave whole. The oversized `try` is documented and load-bearing (`:2-6`), and the `_ClaimState` holder (`:62-79`) documents a real bug the returned-value version caused. Only observation: `_ClaimState` existing at all is evidence the try-block is too wide — but the alternative was worse and was tried.

### `hierarchy/router.py` — 312 LOC
Already governed by `tests/hierarchy/test_router_is_routes_only.py` with `MAX_LINES = 340`. 16 routes, no private helpers, no `select`/`text`, no function-local imports. Only issue is §1-V3. Leave.

### `hierarchy/application/stats.py` — 299 LOC
Two responsibilities: aggregate stats (`folder_stats:40`, `tracked_stats:78`, `weakest_senses:122`, `weakest_tracked_senses:145`, `deck_item_counts:196`) and the history read model (`history_buckets:223-299`, 77 LOC of two raw queries + a shared scope fragment). `history_buckets` is the only function here that talks to `pycil.policy.history` (`:16`) and the only one with a `sense_ids=None` global mode. Target: split `history-buckets.py` out; leaves 220 LOC of cohesive stats. Low urgency.

### `learning/router.py` — 287 LOC / `content/router.py` — 271 LOC
`learning/router.py` is 6 routes of pure field-by-field DTO mapping; the mapping is verbose (`:155-199` is 45 lines for one response) but it is genuinely wire mapping. Consider `SessionStateRead.from_live(...)`/`.from_summary(...)` classmethods to move it onto the DTO. `content/router.py` needs §1-V4/V5/V6 addressed, which removes ~90 LOC from it.

---

## 4. AI-patchwork smells

**P1 — Fully dead functions outside `session_store`.**
`content/application/service.py:36-40` `rename_deck` — **0 src refs, 0 test refs**.
`content/application/service.py:43-45` `delete_deck` — **0 src refs, 0 test refs**.
`content/application/service.py:20-33` `create_deck` — **0 src refs**, 9 test refs (`tests/content/test_deck_membership.py:55,66,75,83,91,99,148,216,257`). The assistant path does *not* use it: `assistant/application/tools.py:117` calls `hierarchy_facade.create_deck`, which calls `hierarchy service.create_node` directly. So `content.create_deck` is a test-only wrapper.

**P2 — Wrappers that only forward.**
- `content/service.create_deck:20-33` → `hierarchy_service.create_node` (adds only `node_type=NodeType.DECK`)
- `content/service.delete_deck:43-45` → `hierarchy_service.soft_delete_node` (adds nothing)
- `learning/domain/fsrs_wrapper.py:18-19` `first_review` → `initial_state`; `:22-25` `next_state` → `update` (adds only the `elapsed_days` call). Module docstring calls itself "a small domain-shaped surface... No new math here" (`:1-5`). Defensible as a seam; `elapsed_days:12-15` is the only real content.
- `session_store.take_generation_slot:838` / `take_grading_slot:843` → `_take_slot:833`. Two limits, two key namespaces — justified.

**P3 — Duplicate logic across files: the terminal-classification scan, twice, byte-equivalent.**
`session_flow.read_live:467-478` and `session_recap.persist:73-80` both iterate `get_admitted`, call `get_progress`, `continue` on `None`, then classify `terminal_reason == "retries_exhausted"` → exhausted, `elif terminal` → completed. `session_flow.py:473-476` even carries the comment explaining why the order matters ("testing `terminal` first would report a failure as a success"); `session_recap.py:77-79` has the same code without the comment. Exactly the divergence risk `cache.delete_prior_defsets_quietly` was created to remove (`cache.py:156-158` documents that precedent). Extract one `classify_admitted_outcomes(redis, session_id) -> (completed, exhausted, per_sense)`.

**P4 — Four separate N+1 `admitted -> get_progress` scans; up to three per request.**
`round_scheduler.round_candidates:132-140`, `has_open_work:147-152`, `has_pending_grade:163-167`, `session_complete:187-195`. `session_complete` scans the admitted set (`:191-194`) and then calls `has_pending_grade` (`:195`), which scans it *again*. `session_flow.next_question` can call `round_candidates` (`:325`), `has_open_work` (`:358`) and `session_complete` (`:362`) in one request → 4 full scans, each `1 + N` Redis round-trips at `N = target_words_per_session` (default 10 per `policy.DEFAULT_TARGET_WORDS_PER_SESSION`). Plus `read_live:463-468` and `session_recap.persist:70-74` and `end_session:795-797` and `reopen_bound_delivery:395-397` — 8 sites total re-deriving the same map.

**P5 — Boolean flag forking behavior, four copies of the same epilogue.**
`commit: bool = True` at `hierarchy/service.py:59` (`move_node`), `:84` (`soft_delete_node`), `:107` (`set_visibility`), and `content/service.py:68` (`remove_sense`). Each body ends in the identical two-branch block:
```
if commit: await session.commit(); [refresh]; await cache.delete_prior_defsets_quietly(prior)
else:      await session.flush();             cache.defer_invalidation(session, prior)
```
at `hierarchy/service.py:74-80`, `:93-98`, `:121-127`, `content/service.py:75-82`. Four copies; only `content/service.py:79-81` carries the comment explaining why the deletion cannot happen pre-commit. `cache.flush_deferred_invalidations` (`cache.py:142-146`) is the intended drain and has exactly 1 src caller.

**P6 — Three parallel tables over one closed set of 4 render types.**
`question_delivery._READY_CLASSES:21-26` (dict name→class), `presentation_payload:29-50` (if/isinstance chain, 4 arms), `render_format:54-72` (if/isinstance chain, 4 arms, same order). Adding a render type means editing three places in one file, and two of them raise different error codes (`lexi_question_presentation_invalid` vs `lexi_render_format_unsupported`). One table of `{type: (name, ready_cls, payload_fn)}` collapses all three.

**P7 — Growing if/elif that is *not* yet a polymorphism case.** `round_scheduler.eligible_requirement:51-120` branches on `purpose in {"due","new"}` × open-retry × exposed × passed, returning a tiered `Requirement`. Flagged here for the record; recommendation is **leave** (§5).

**P8 — Defensive re-validation of already-validated data.**
- The same `int(question_id)` coercion runs twice per delivery on the same object: `session_flow._try_deliver:409-413` (silently defers on failure) then `question_delivery.ready_question:90-96` (raises 503 on failure) — `router.py:230` calls the second immediately after the first succeeded. Two different failure semantics for one impossible-by-then condition.
- `planning.settings_for_user:77-79` clamps `max(1, ...)` on read, while `domain/schemas.py:33-34` enforces `ge=1` on write and (per `:74-76` and `schemas.py:29-31`) a CHECK constraint enforces it in the DB. Triple-guarded, documented as deliberate — leave, but note it as the pattern.
- `_ClaimState` (`answering.py:62-79`): a `__slots__` holder class whose only purpose is smuggling one enum out through an exception. Documented and load-bearing, but it is a symptom of the 50-line `try` at `:146-195`.

**P9 — Single-use helper that adds a layer without adding meaning.** `dashboard._engaged():57-58` returns a 2-tuple, called once at `:63` and immediately unpacked into `engaged_a, engaged_b`, then used twice as `engaged_a | engaged_b` (`:69`, `:86`). The stated goal — "expressed once here because both the count and the average must agree on it" — is achieved; the tuple-and-unpack is the awkward part. A module constant or a function returning the `or_` expression would say it directly. (Contrast: `reads.readable_path`, `owned_children_page`, `tracked_sense_ids`, `weakest_rows` each have exactly 1 src caller but exist to satisfy `test_router_is_routes_only` — justified extraction, not smell.)

**P10 — Redundant constant reassignment.** §1-V3, `hierarchy/router.py:44`.

**Interfaces with exactly one implementation:** `LexiReader` / `LexiWorkerEngine` (`pycil/ports/lexi.py`) are consumed across all three modules. `tests/learning/fakes.py` exists and `tests/learning/test_resolver.py`, `test_apply_verdict.py` pass fakes/graders in, so a test double does exist → the port is earning its keep. **UNVERIFIED:** I did not read `pycil/ports/lexi.py` or `lexi_provider.py`, so the exact number of production implementations is unconfirmed.

---

## 5. Pattern opportunities — with skepticism

### R1 — Commit-boundary seam replacing the `commit: bool` flag (recommended)
(a) **Problem:** 4 functions fork on a boolean and duplicate a commit/defer epilogue (P5); the caller must know to call `cache.flush_deferred_invalidations` afterward, and nothing enforces it.
(b) **Why current code is bad:** the flag is a behavioral fork in a *mutation* path, the two branches differ in cache-correctness semantics, and there are 4 copies of it — the classic shape that drifts. Only 1 of the 4 carries the explanatory comment.
(c) **Pattern:** Unit-of-Work with post-commit hooks. Services always `flush()` and register `prior` as a post-commit action; whoever owns the transaction commits and drains. `cache.defer_invalidation`/`flush_deferred_invalidations` (`cache.py:121-146`) is already 80% of this, stored on `session.info`.
(d) **Trade-off:** the commit becomes implicit at the service call site; a reader of `move_node` no longer sees `await session.commit()`. Requires one drain point per entry surface (router dependency + assistant runner) — miss one and invalidation silently stops happening, which is the same failure mode the current explicit flag makes visible.
(e) **Why it beats the simpler fix:** the simpler fix — extract `_finish(session, prior, commit)` as a shared 6-line helper — removes the duplication but keeps the boolean fork and the caller obligation. It is genuinely a decent 80% option and is *lower* risk. Recommend the simple helper first, and only adopt UoW if a third entry surface appears.

### R2 — Load the session state once (recommended, and it is not a pattern)
(a) **Problem:** P4 — 8 sites re-deriving `{sense_id: (purpose, SenseProgress)}`, up to 4 scans per `/next`.
(b) **Why bad:** `1 + N` Redis round-trips per scan, and the 4 predicates in `round_scheduler` cannot be tested without a Redis fake even though 3 of them are pure decisions over the loaded map.
(c) **Fix:** one `load_admitted_progress(redis, session_id) -> AdmittedProgress` in the store; `round_candidates`, `has_open_work`, `has_pending_grade`'s Redis half, `session_complete`, `read_live`, `session_recap.persist` all become pure functions over it (P3 collapses too). This also removes `session_complete`'s double scan.
(d) **Trade-off:** one snapshot per request instead of per predicate — the predicates then see a consistent-but-slightly-older view. Today they each see a fresher view, which sounds better but is not: `session_complete` currently reads the set twice within one call and can already observe two different states. A single snapshot is *more* coherent.
(e) **Why not Repository/Aggregate pattern:** a plain function returning a dataclass gets the entire benefit. Introducing a `SessionAggregate` with behavior would relocate the terminality rules again, which is a separate decision (§1-V2).

### R3 — One render-type table (recommended, small)
(a) P6. (b) Three edit sites per new type, two inconsistent error codes. (c) A single module-level dict `{render_cls: (wire_name, ready_cls, payload_builder)}`. (d) Slight indirection; `isinstance` chains are more grep-friendly than a dict lookup. (e) Beats "just keep them in sync" because the set is closed and the file already proves the sync is manual — `render_format`'s docstring (`:56-63`) exists solely to explain that it is not a duplicate of the thing above it.

### R4 — Delete before refactoring (recommended, do first)
Not a pattern. §3-S1 (7 functions, ~180 LOC in `session_store.py`) + P1 (`content/service.rename_deck`, `delete_deck`, and a decision on `create_deck`). Every other proposal in this section gets cheaper afterwards: two of the three §1-V2 duplicate-rule sites disappear, and `session_store` drops to ~680 LOC before any split. The blocker is that 6 of the 7 have tests, so deleting the function means deleting live tests — which requires confirming the functions are not a planned path (see Unresolved).

### R5 — Move `AdmittedSense` / `SenseProgress` to `learning/domain/` (recommended, mechanical)
Fixes §1-V1. Precedent and rationale already written by this codebase for the identical situation (`hierarchy/domain/vocabulary.py:1-11`). Pure import churn, ~6 call sites.

### Looked for a pattern and concluded: leave it simple

- **`round_scheduler.eligible_requirement` (P7) — leave.** Pure, no I/O, closed 2-value `purpose` domain, 4 tiers as int constants (`:32-36`), and directly unit-tested (`tests/learning/test_round_scheduler.py`). A Strategy/`RequirementRule` hierarchy would spread 60 lines of decisions across 4 classes plus a registry for zero new behavior, and would make the priority order — currently one `sort` key at `:141` — an emergent property of registration order.
- **`answering._apply_now` / `_defer` — leave.** Looks like Strategy on `evaluation.status`, but there are exactly two statuses, and the *difference between them is the compensation semantics*, which is the module's entire subject matter. Polymorphism would hide the `_Claim` transitions in subclasses, precisely the drift `answering.py:63-74` documents as having already caused a bug.
- **The `Delivered | RoundBreak | NoQuestionYet` union + router isinstance dispatch — leave.** Already the right design (data-not-response-models, `session_flow.py:13-15`). Do not add a Visitor or a `to_response()` method; the latter would put HTTP shapes back into application.
- **No Repository layer for any of the three modules — leave.** `AsyncSession`-as-parameter is uniform across all three modules *and* the assistant facades (`assistant/application/hierarchy_facade.py`, `content_facade.py`). Tests call service functions with a real session directly (`tests/content/test_deck_membership.py:55`), so repositories would buy no test isolation and would touch every call site in the app.
- **`hierarchy/stats.py` raw SQL — leave.** Documented plan-shape reason (`stats.py:4-5`, `:22-23`, `:246-249`). Converting to ORM would risk the `ANY(CAST(...))` plans these were written for.
- **`content/service._require_live_deck` FOR UPDATE + type check (`:141-151`) — leave** (fix only the function-local imports).
- **Redis acquisition inconsistency (`get_redis()` global in `hierarchy/cache.py` vs parameter in learning) — leave.** 3 call sites, and the cache is already the layer where Redis failures are swallowed by design. Not worth a DI container; if anything, make `cache.py` take the client when something else forces that file open.
- **`hierarchy` twin readability rules (Python `can_read_node` + SQL `_READABLE_DECKS_SQL`) — leave.** Normally a duplication finding; here the SQL form is required for set-at-a-time filtering and `tests/hierarchy/test_readability_rule_parity.py` pins them. Do not attempt to unify.
- **`learning/router.py` verbose DTO mapping — leave for now**, or at most move to `SessionStateRead.from_live/.from_summary` classmethods. No pattern.
- **`folder_items` offset pagination (`hierarchy/router.py:217-223`) — flag, don't pattern.** It slices an already-fully-materialized list, so pagination saves only the `get_senses` call. Either accept that (it is cached) or make it keyset like `owned_children_page`. Needs a product call, not a pattern.

---

## 6. Effort / risk table

| # | change | size | regression risk | test coverage today | independent? |
|---|---|---|---|---|---|
| R4a | delete `session_store` dead fns: `pass_checkpoint`, `open_retry`, `lock_score`, `set_exposed`, `add_excluded`, `mark_round_used`, `mark_fsrs_applied` (~180 LOC) | M | low (0 src refs verified) — but 28 test refs must be deleted with them | `tests/learning/test_session_store_cas.py` + others exercise them directly; the *live* replacements are covered by `test_score_state_engine.py`, `test_fsrs_idempotency_concurrency.py`, `test_aborted_answer_recovery.py` | yes; do first |
| R4b | delete `content/service.rename_deck`, `delete_deck` | S | low (0 refs anywhere) | none | yes |
| R4c | decide `content/service.create_deck` (delete + rewrite 9 tests, or keep as documented API) | S | low | 9 tests in `test_deck_membership.py` | yes |
| R5 | move `AdmittedSense`/`SenseProgress` to `learning/domain/` | S | low (imports only) | `test_round_scheduler.py`, `test_planning_admission.py` construct them | yes |
| V3 | delete `hierarchy/router.py:44` + duplicate comment | S | low | `test_global_analytics.py:271` monkeypatches the same name — re-run it | yes |
| P8a | remove the duplicate `int(question_id)` coercion (`session_flow:409-413` vs `question_delivery:90-96`) | S | med — the two paths raise differently; must confirm which failure mode `/next` should show | `test_delivery_payload_leak.py`, `test_resolver.py` | yes |
| R3 | one render-type table in `question_delivery.py` | S | low | `test_delivery_payload_leak.py:37,46` covers both functions | yes |
| P9 | inline `dashboard._engaged()` | S | low | `test_dashboard.py` | yes |
| V1-fix | function-local imports out of `content/application/service.py:144,148` and `generation_quota.py:52` | S | low | `test_deck_membership.py` | yes |
| P3 | extract the shared terminal-classification scan (`session_flow:467-478` + `session_recap:73-80`) | S | low | `test_session_read.py`, `test_session_recap.py` cover both callers | yes |
| R1-simple | extract shared `_finish(session, prior, commit)` helper, 4 call sites | S | med — touches every hierarchy/content mutation | `test_cache_generation_interleavings.py`, `test_tree_reference_cache_integrity.py`, `test_deferred_cache_invalidation.py` | yes |
| R1-UoW | full Unit-of-Work with post-commit hooks | L | **high** — a missed drain point silently stops cache invalidation | same as above, plus `test_single_cached_subtree_read.py` | no; supersedes R1-simple |
| R2 | single `load_admitted_progress` snapshot; 4 predicates become pure | M | med — changes read-consistency timing inside `/next` | `test_round_scheduler.py` (2 tests only: priority order, session_complete), `test_session_read.py`, `test_session_recap.py`. Thin for the number of call sites moved | yes, but do after R4a |
| S1-split | split `session_store.py` into 4 files + extract `learner-rate-slots.py` | M | low-med (pure moves; the rate-slot extraction is the safest part) | `test_session_store_cas.py`, `test_supply_task_submission.py`, `test_submit_answer_pending.py` | after R4a |
| S2 | move `read_live` + its 2 view dataclasses out of `session_flow` | S | low | `test_session_read.py` | yes |
| S3 | move `request_supply` to `question-supply-request.py` | S | low | `test_supply_task_submission.py` | yes |
| V4 | extract `content/router.request_word` orchestration into `content/application/` | M | med — quota compensation paths are subtle (`router.py:103-107`) | `test_word_generation_tool_uses_durable_tasks.py` covers the assistant twin, not this route directly | yes |
| V5 | move the sense-detail authorization composition into `content/application/` | S | med — it is an authorization boundary | `test_sense_detail.py`, `test_route_auth_coverage.py` | yes |
| V6 | move `_sense_content`/`_sense_detail` out of `content/router.py`; add a `test_router_is_routes_only` for content | M | low | `test_sense_detail.py`, `test_deck_membership.py`, `test_response_camel_case.py` | yes |
| V2 | extract `classify_checkpoint(...)` from `service.py:131-147` into `learning/domain/` | M | med — it is the correctness core | `test_score_state_engine.py`, `test_fsrs_idempotency_concurrency.py` — strongest coverage in the module | after R4a (which removes 2 of 3 duplicate sites) |
| S4 | split `history_buckets` out of `hierarchy/stats.py` | S | low | `test_history.py`, `test_global_analytics.py` | yes |

Suggested order: R4a/R4b/R4c → R5, V3, V1-fix, P3, P9, R3, S2, S3 → S1-split → R2 → V2 → V4/V5/V6 → R1-simple. R1-UoW and S4 optional.

Coverage note: 143 tests / 19 files for `learning`, 66 / 14 for `hierarchy`, 42 / 7 for `content`. The thinnest coverage relative to blast radius is `round_scheduler` (2 tests for 4 predicates consumed by `/next`) and `hierarchy/application/reads.py` (only reached via `test_global_analytics.py`).

---

## Unresolved questions

1. **Are the 7 dead `session_store` functions a planned path or residue?** `pass_checkpoint`/`open_retry`/`lock_score` look like the pre-`apply_checkpoint_projection` design, and `service.py:14` still describes `lock_score` in its module docstring as the advisory fast-path — so the docstring documents a function nothing calls. Deleting them means deleting 28 test references. Confirm before R4a.
2. **Is `content/application/service.create_deck` intended as a public seam** (a deck-creation entry point that will grow deck-specific behavior), or should the 9 tests move to `hierarchy_service.create_node`? Same question for `rename_deck`/`delete_deck`, which have no references at all.
3. **Which failure semantics should a non-integer `question_id` produce** — the silent defer at `session_flow.py:409-413` or the 503 at `question_delivery.py:90-96`? Both are on the same request path; one must win.
4. **Is `folder_items` offset pagination (`hierarchy/router.py:217-223`) acceptable** given it slices an already-materialized cached list, or should it be keyset like `owned_children_page`?
5. **Should the terminality rules (`REQUIRED_CHECKPOINTS`, `MAX_RETRIES_PER_CHECKPOINT`) live in `learning/domain/`** rather than being applied inside `session_store.apply_checkpoint_projection`? Moving them changes the layer that writes Redis state and is the only §1 violation whose fix is not mechanical.
6. **UNVERIFIED:** I did not read `pycil/ports/lexi.py` / `lexi_provider.py`. The claim that `LexiReader` has more than one implementation rests on `tests/learning/fakes.py` existing and fakes being injected in tests — the production implementation count is unconfirmed.
7. **UNVERIFIED:** I did not run the test suite. All coverage claims in §6 are from filename/import/reference analysis, not from execution or coverage measurement.
