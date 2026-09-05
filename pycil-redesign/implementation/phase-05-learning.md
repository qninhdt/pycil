---
phase: 5
title: "Learning"
status: pending
priority: P1
effort: "4-5d"
dependencies: [1]
---

# Phase 5: Learning

## Overview

Split strength and depth into two independent axes, delete the checkpoint state
machine, and replace the mastery-keyed difficulty sampler with a depth-keyed one.
The largest single deletion in the redesign and the one that removes a whole class of
defect rather than a defect.

## Requirements

**Functional**

- Two axes (`B1`): one answer emits a strength signal and a depth signal.
- Strength stays FSRS with published weights, binary Again/Good (`B2`, `B3`).
- Depth ladder: streak of 2 to advance, one wrong to retreat, floor 1 (`B5`).
- A correct answer **below** depth earns `Good` and moves depth **not at all**
  (`B7`); a wrong answer below depth still retreats (`B8`).
- `serve_level` sampled from a window around `depth_level`, not equal to it (`B6`).
- One question, one grade, one FSRS update (`B9`) — no checkpoints, no retry budget,
  no tiers, no disqualifier.
- A wrong answer returns the sense later as an **ungraded** re-ask at the level that
  was failed, once per session (`B10`).
- New-sense entry is level 1 **by definition**, not sampled; that first graded answer
  sets `scheduled` and depth 1 either way.
- Session length derived, rounds are pagination (`B11`).
- "Learned" is `status = scheduled` (`B12`).
- Stage names render from `depth_level` (`B13`).

**Non-functional**

- The FSRS module's diff is **empty**. Its weight vector keeps every published index.
- One memory update per sense per session, enforced durably.
- The answer write stays a constant number of primary-key statements in one
  transaction.

## Architecture

```text
answer
  ├─► WHEN — FSRS. wrong → Again · correct → Good
  │     → stability, difficulty, next review
  │
  └─► WHAT — depth ladder
        wrong                     → depth − 1 (floor 1), streak 0
        correct, served == depth   → streak + 1; at 2 → depth + 1, streak 0
        correct, served <  depth   → unchanged
```

**The sampling table**, keyed on depth rather than on a strength proxy:

| `depth_level` | L1 | L2 | L3 | L4 |
|---:|---:|---:|---:|---:|
| 1 | 1.00 | — | — | — |
| 2 | 0.40 | 0.60 | — | — |
| 3 | 0.10 | 0.30 | 0.60 | — |
| 4 | — | 0.30 | 0.45 | **0.25** |

The machinery it replaces is **kept**: the band type, the sum-to-one assertion at
import, the injectable sampler. Only the lookup key and the numbers change. The
mechanism was never the defect; keying it to a memoryless function of strength was.

`p(L4) = 0.25` *is* the level-4 rate limit — one mechanism instead of two. The
numbers are `uncalibrated`; the measurement that settles them is the rubric grader's
false-negative rate.

**The re-ask** is what keeps the teaching after the machinery goes. A wrong answer
does two separate things: it grades once, durably; and it returns the sense in a
later round as an ungraded item at the level that was failed. That item writes
**nothing**. A graded-set in session state enforces once-per-sense.

## Related Code Files

**Modify**

- `apps/api/pycil/policy/policy.py` — re-key the table to `depth_level`; keep the
  band type, the assertion, and the sampler
- `apps/api/pycil/policy/sense_state.py` — `depth_level`, `depth_streak` (the columns
  exist from phase 1)
- `apps/api/pycil/learning/` — flatten to `models/service/router/schemas` (`A2`)
- the answer path — two axes, one grade, the graded-set
- the round scheduler — shrink to "what is eligible this round", no tiers
- session store — add the graded-set; delete checkpoint and retry state
- `apps/api/pycil/learning/application/dashboard.py` — "learned" is
  `status = scheduled`

**Delete**

- the checkpoint constants and the retry budget
- the four-tier priority ordering
- `disqualifier`, `open_checkpoint`, `open_failed_round`, `retries_used`
- the tests whose subject is gone: planning admission, the round scheduler's tiers,
  the score/state engine

**Do not touch**

- `packages/shared-py/shared/fsrs/` — the diff must be empty

## Implementation Steps

1. Re-key the table: replace the mastery-band lookup with a `depth_level` index, keep
   the band type and the import-time assertion, and load the new numbers.
2. Write the depth ladder as a pure function over `(depth_level, depth_streak,
   served_level, correct)` returning the next pair. Unit-testable with no I/O.
3. Rewrite the answer path: resolve the served level, grade once, apply both axes,
   record the response. Delete the disqualifier entirely — a correct answer is
   correct.
4. Add the graded-set to session state and make every later encounter of a graded
   sense ungraded.
5. Implement the re-ask: on a wrong answer, re-admit the sense for a later round at
   the level that was failed, once.
6. Add the new-sense entry rule: depth 0 plus `new` means level 1 unsampled, and the
   first graded answer sets `scheduled` and depth 1.
7. Shrink the round scheduler to eligibility only, and shuffle within a round subject
   to two constraints: exposure before its graded question, and a re-ask in a later
   round than its failure.
8. Derive session length; keep the break as a state the server names.
9. Change "learned" to `status = scheduled` in every reader.
10. Delete the checkpoint machinery and every test whose subject it was.
11. Grade free text synchronously under the delivery timeout; timeout writes no
    answer, review, strength, or depth effect and leaves the item answerable.

## Todo

- [ ] Table re-keyed to `depth_level`, machinery kept
- [ ] Depth ladder as a pure function
- [ ] Answer path: one grade, two axes
- [ ] Disqualifier deleted
- [ ] Graded-set in session state
- [ ] Ungraded re-ask, once per sense
- [ ] New-sense entry at level 1 unsampled
- [ ] Round scheduler reduced to eligibility
- [ ] Shuffle with two ordering constraints
- [ ] Session length derived
- [ ] "Learned" is `status = scheduled`
- [ ] Checkpoint machinery and its tests deleted
- [ ] Free-text success is settled before completion; timeout leaves no partial effect
- [ ] FSRS module diff empty
- [ ] `learning.md` §12 covered by named tests

## Success Criteria

- [ ] One answer produces exactly one review-log row
- [ ] A correct answer never produces `Again` under any supply condition
- [ ] Depth advances only on a clean pass at the served depth
- [ ] Depth retreats on a wrong answer at any level; floor 1
- [ ] Depth 0 never coexists with `status = scheduled`
- [ ] An ungraded re-ask writes nothing
- [ ] At most one ungraded re-ask per sense per session
- [ ] A session completes with a grade still pending
- [ ] The recap survives the loss of session state
- [ ] Stage name from depth, `mastery` from stability, independently assertable
- [ ] `git diff packages/shared-py/shared/fsrs/` is empty
- [ ] `learning.md` §12 fully covered by named tests

## Risk Assessment

**Deleting the checkpoint machinery removes the re-ask unless it is deliberately
rebuilt.** This is the trap: the machinery was wrong, the behaviour it produced was
right. Signal: a learner answers wrong and never sees the word again in that session
— which reads as correct code and is a pedagogical regression. Response: the re-ask
is a success criterion, not a nice-to-have.

**The sampling numbers are guesses.** Signal: none available — observability is
deliberately absent (`O7`). Response: recorded as `uncalibrated` with the measurement
named. The defensible claim is not the numbers but the keying: a window around a
remembered achievement is recoverable when mis-tuned, whereas a memoryless function
of strength was wrong in kind.

**Level-4 supply is one item with no variation source.** A learner at depth 4 meets
one prompt repeatedly. Signal: obvious to any learner who reaches depth 4. Response:
`p(L4) = 0.25` bounds the exposure, and phase 6 decides whether the per-demand count
is honoured — which is the real fix.

**Two definitions of "learned" are currently rendered on one screen.** Changing to
`status = scheduled` changes a number the learner sees. Response: it is the right
predicate — the justification for the looser one was a row created by burying, and
burying is deleted in phase 1.
