# Phase 5 Code Review — Learning Mode & ELO

**Reviewer:** code-reviewer (Staff Engineer pre-landing review)
**Date:** 2026-05-24
**Scope:** ELO module + service + API + web runner. Acceptance criteria 1-7 + targeted regressions.

## Verdict

**BLOCKER FOUND.** One Critical schema mismatch will fail every session at the first ELO write. Two Important findings concern the v1 contract (R-always-1 in service path, comprehension variable shadowing). Otherwise implementation matches the plan and the formal ELO tests are sound.

---

## Critical

### C1. `user_term_stats.elo` column does not exist — `mastery_score` is the canonical name

Schema (alembic/versions/0001_init.py:227) declares:

```sql
mastery_score INT NOT NULL DEFAULT 1000,
```

Service (`services/learning_service.py`) reads/writes `elo`:

- `learning_service.py:138-141` `SELECT definition_id, elo FROM user_term_stats ...`
- `learning_service.py:147-149` `int(r.elo)`
- `learning_service.py:278-292` `INSERT INTO user_term_stats (... elo ...) ... ON CONFLICT ... SET elo = EXCLUDED.elo`

Asyncpg will raise `UndefinedColumnError: column "elo" of relation "user_term_stats" does not exist` on the first term-reviewed event. This breaks acceptance criteria #2, #4, #5, #6, #7.

**Threat-model trace:** every successful Q-correct triggers `_persist_review` → guaranteed 500 on first session for any new user. Cold-start hydration also fails on `start_session` if any row exists in `user_term_stats` for the user.

**Fix options (pick one — flag to user, do not auto-revise):**
1. Rename SQL references in `learning_service.py` to `mastery_score` (keeps schema stable, smallest patch).
2. Add an alembic migration `0003_rename_mastery_score_to_elo` (renames column; matches the code's vocabulary, but mutates schema the user already locked in 0001_init).

`mastery_score` was the locked schema name in 0001_init so option 1 is the conservative choice. Option 2 is also defensible since the plan + idea.md §4.3 use the term "ELO" throughout. **Surface to user — do not silently flip.**

Also note `user_term_stats.review_count` exists in schema but is never incremented in `_persist_review`. Not blocking (not in acceptance), but flag for v0.2 stats UI.

---

## Important

### I1. ELO never decreases for a given term in the v1 service path

`learning_service.py:392-396`:

```python
elo_old = int(tracking["elo_at_start"])
R = elo_mod.realized_score(tracking["correct_firsts"], _REQUIRED_CORRECT_FIRSTS)
```

ELO compute is only entered when `correct_firsts >= 2` (line 390). At that moment `correct_firsts == 2` and `Q == 2`, so `R == 1.0` **always**. Wrong answers do not trigger the compute — they only delay it. With `E ≤ 1.0`, `Δ ≥ 0` always, so:

- Acceptance #3 ("Wrong answers do NOT increase interval, Δ<0 → interval unchanged") is satisfied **trivially** (the path is never taken in practice).
- Acceptance #4 ("Correct answers grow interval per F^Δ/S") is satisfied.

**Why this matters:** the elo module's `new_interval_seconds(...)` failure branch (line 90) is dead code in production. The synthetic test (`elo_test.py:112-131`) does exercise R∈{0, 0.5, 1}, so the formal coverage on `elo.py` is real. But anyone reading the service path will see "ELO only ever goes up" — surprising.

**Trace to threat model:** not a bug per spec ("Q correct first-answers required to mark term reviewed" + "only first answer counts toward R"). Document in code or surface a future-v0.2 question for partial credit. Recommend a comment at `learning_service.py:393` explaining R is always 1.0 in v1.

### I2. Variable-name collision: `d` shadowed inside list comprehension

`learning_service.py:401` then `learning_service.py:420-422`:

```python
d = elo_mod.elo_delta(R, E, T)
...
state["round_queue"] = [
    d for d in state["round_queue"] if int(d) != definition_id
]
```

Python 3 list comprehensions have their own scope, so the outer `d` (the elo delta int) is **not** clobbered post-comprehension — but reading this is a trap. Rename comprehension var to `did`:

```python
state["round_queue"] = [did for did in state["round_queue"] if int(did) != definition_id]
```

Minor correctness OK; readability fix.

### I3. Polling `setTimeout` has no cleanup

`components/learning-session-runner.tsx:49`:

```ts
setTimeout(() => void fetchNext(), POLL_DELAY_MS);
```

If the user navigates away while the poll is pending, the timer fires after unmount → `setState` on unmounted component → React warning, plus a stray API call. Use a ref + `clearTimeout` in `useEffect` cleanup, or an AbortController on the fetch. Not blocking for v1 launch but easy to fix.

---

## Minor

### M1. Double feedback render

`learning-session-runner.tsx:67-81` calls `submitAnswerAction`, returns the result to `MultipleChoiceCard.onCheck` (which renders its own internal feedback state) AND sets `phase = feedback` (which renders `FeedbackView`). Brief flash where both visible. UX cleanup, Phase 6.

### M2. `_DEFAULT_ROUND_SIZE = 5` ignores `deck_attributes.settings`

Plan §"Round Logic" specifies P configurable via `deck_attributes.settings`. Service hardcodes 5. Acceptable for v1 (no UI to set it anyway) — flag for v0.2.

### M3. New Redis connection per call

`_redis()` in `learning_service.py:40-41` instantiates a fresh `Redis.from_url(...)` per `start_session`/`next_question`/`submit_answer` and aclose()s it. Functional but wasteful; existing pattern in `question_service` may already provide a pooled client — align with that. Not a regression, just inconsistent.

### M4. `correct_index` exposed when `selected_index` validation fails

`schemas/learning.py:37`: `selected_index: int = Field(ge=0, le=3)`. A 422 response includes the `correct_index` only after a valid submission. The 422 path itself does not leak — fine. Noting only because pyright/lint may flag the tight coupling to MCQ's 0-3 range; once Write/Fill ship in v0.2 this needs to relax.

### M5. `review_count` never incremented

`_persist_review` upserts `elo, last_review_date, next_review_date, interval_seconds, mastery_level` but ignores `review_count`. Stats UI in Phase 6 will show 0 reviews always. Add `review_count = user_term_stats.review_count + 1` to the UPDATE branch and `1` to the INSERT branch.

### M6. `expected_score` hardcoded to `[INITIAL_ELO]`

`learning_service.py:396`: `E = elo_mod.expected_score(elo_old, [INITIAL_ELO])`. Plan §"Question ELO" says all v1 questions are 1000 (acceptable). Once `questions.data.elo` becomes meaningful in v0.2, swap in the actual question elo. Documented elsewhere in the plan; flag here for traceability.

---

## Acceptance Criteria Trace

| # | Criterion | Status |
|---|-----------|--------|
| 1 | All ELO unit tests pass; coverage on `elo.py` = 100% | ✅ tests cover every public fn + bounds + cold-start + clamps + synthetic |
| 2 | Cold-start writes `user_term_stats` with ELO ≈ 1000 ± Δ | ❌ blocked by **C1** (column `elo` missing) |
| 3 | Wrong answers do NOT increase interval | ✅ trivially (path never invoked, see **I1**) |
| 4 | Correct answers grow interval per F^Δ/S | ❌ blocked by **C1** at write time; math itself is correct |
| 5 | Mastery level updates on every term-reviewed | ❌ blocked by **C1** |
| 6 | Session state survives pycil-core restart (Redis) | ✅ all state in Redis, EX 4h, lock + state both keyed by session id |
| 7 | Synthetic 100-session test bounded | ✅ `elo_test.py:112-131` asserts ELO ∈ [0, 3000] and interval < 70 days |

**Net:** 4/7 criteria fail at runtime until **C1** is resolved.

---

## Regression Checks (Phases 1-4)

- **Jobs router** — untouched; `main.py:8-11` still imports and includes. ✓
- **Terms route** — no changes to `apps/pycil-core/pycil_core/api/routes/terms.py`. ✓
- **Question generation / MCQ check** — `question_service.get_or_generate` reused as-is in `next_question` (line 231-233). MCQ check uses the same `MultipleChoiceQuestion.check_answer` contract from `packages/shared-py/shared/questions/multiple_choice.py:62-75`. ✓
- **Term-card** — unchanged; `dashboard/[nodeId]/page.tsx` only adds a "Study this deck" form above the term list. ✓
- **MCQData type** — `apps/web/lib/types.ts:73-79` mirrors the server schema unchanged. ✓

No phase-1-4 regressions detected.

---

## Targeted Spot-Checks

- **`_RELEASE_LUA` correctness** (`learning_service.py:66-72`) — GET == ARGV[1] guard, DEL only on match. Standard SET-NX-EX + Lua-CAD pattern; correct. Lock TTL 5s safe for sub-second answer flow.
- **TZ-awareness** — `last_review_date TIMESTAMPTZ` in schema; `_previous_review` does `datetime.now(tz=utc) - row.last_review_date`. asyncpg returns TIMESTAMPTZ as tz-aware `datetime` → subtraction is safe. ✓
- **`= ANY(:ids)` with list[int]** — asyncpg unpacks Python list to PG array; standard pattern, no driver issue. ✓
- **`elo_at_start` locked at session start** — multiple terms in one session share the snapshotted starting rating per term (independent per definition_id). v1 has no aggregate user ELO; this matches the plan ("question.elo[1000]" expected score). ✓
- **`session_complete` branch** (`learning_service.py:216-225`) — only triggers when `round_queue` empty AND `_next_round_queue()` empty. `_next_round_queue` filters for `not completed` → returns [] only when all terms completed. ✓ no premature finish.
- **Multi-tab races on submit_answer** — `_acquire_lock` runs before `_load_state`; mutations + `_save_state` inside the try, release in finally. ✓
- **Web server action with redirect** (`dashboard/[nodeId]/page.tsx:168-177`) — Next.js 15 server actions support `redirect()` (it throws a `NEXT_REDIRECT` signal handled by the runtime). ✓
- **Term-completed double-drop** — line 384 pops front; lines 420-422 filter again. Defensive double-drop, not a bug, but see **I2** for var-name nit.

---

## Positive Observations

- ELO module is genuinely pure — no IO, no datetime, no random — and the test file covers each function plus a synthetic stochastic run. Matches plan §"Implementation Steps" #1.
- Per-session Redis lock is correctly the GET-equals + DEL-via-Lua pattern, not the naive `DEL` race.
- `_initial_state` snapshots `elo_at_start` per term so concurrent term progression doesn't poison the rating math.
- `term_selection.py` single SQL with three UNION ALL branches keeps prio + nrd ordering inside the planner; no N+1.
- Lazy import of `MultipleChoiceQuestion` (`learning_service.py:338`) keeps shared-py import cycles avoided. Matches the question_service pattern at `services/question_service.py:159`.
- Pyright will still flag `import shared.questions...` as unresolved (existing project quirk per phase-3/4 reviews) — no new noise.

---

## Recommended Actions

1. **C1 — Resolve schema/code naming mismatch.** Pick rename-in-code (smaller patch) vs migration (matches plan vocabulary). **Surface to user before applying.**
2. Increment `review_count` in `_persist_review` (M5) — one-liner.
3. Rename comprehension var `d → did` at `learning_service.py:420-422` (I2).
4. Add cleanup ref + `clearTimeout` in `learning-session-runner.tsx` (I3).
5. (Optional) Inline comment at `learning_service.py:393` clarifying R==1.0 invariant in v1 (I1).

Items 2-5 are trivial follow-ups; item 1 is the only blocker.

---

## Metrics

- ELO module coverage: 100% (all public fns + cold-start + clamps + synthetic, per `elo_test.py`).
- New lint signal: none beyond expected pyright "shared not resolved".
- Files touched: 13 (8 pycil-core + 5 web). LOC delta: ~700.

---

## Unresolved Questions

- **C1 fix direction** — rename column in code (keep schema) or migrate column (match plan vocabulary)? User-locked decision area; do NOT auto-flip.
- **`review_count` semantics** — is it "term-reviewed events" (Q-correct-firsts hits) or "questions answered"? Plan doesn't specify. Default: increment on each term-reviewed event for stats UI parity.
- **Is "Study this deck" supposed to be visible when the deck has no enriched terms?** Currently the button always shows; clicking with 0 due/new/upcoming returns 400 `no_terms_to_study`. Phase 6 polish, not a v1 blocker.
