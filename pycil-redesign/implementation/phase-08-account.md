---
phase: 8
title: "Account"
status: pending
priority: P2
effort: "3-4d"
dependencies: [7]
---

# Phase 8: Account

## Overview

Plans, the credit ledger, and a deletion order that aborts loudly rather than
cascading silently. The economic rule is one sentence — charge for what cannot be
reused, give away what enriches the commons — and every mechanism here follows from
it.

Depends on phase 7 because the deletion order walks the node tree, and on phase 5
because credit exhaustion degrades through the sampling table.

## Requirements

**Functional**

- Two feature tiers plus a top-up pack (`P2`); library, tree, subtree study, review
  volume, deterministic grading, publishing, and export are unlimited on both (`P3`,
  `P4`).
- Credit gates exactly two things: level-4 grading and agent turns (`P5`).
- One pool denominated in token work, displayed with a human estimate (`P6`).
- Balance checked at submit, **debited at completion** (`P7`); a provider failure
  debits nothing.
- Debits append-only with `UNIQUE (kind, reference_id)` (`P8`).
- The period resets by **elapsed time on the next debit**, with no scheduled job
  (`P9`).
- Exhaustion degrades along the existing supply-shortfall path (`P10`): the sampler
  drops level 4, a correct answer still earns `Good`, depth simply does not advance.
- Word generation **never charged**; rate-limited per day by plan (`P11`).
- Export complete and free on every plan; no dictionary content.
- Deletion hand-ordered with `NO ACTION` foreign keys (`O11`), aborting loudly on a
  forgotten table.

**Non-functional**

- No cron can fail in a way that becomes a billing incident.
- Deletion leaves the shared dictionary untouched.

## Architecture

```text
user_credits                       credit_debits
  user_id      PK                    id · user_id · kind · reference_id
  plan                               amount · created_at
  period_start                       UNIQUE (kind, reference_id)
  period_used
  topup_balance   ← does not expire with the period

balance = grant(plan) − period_used + topup_balance
```

**Why charge at completion.** Reserve-settle-release needs a reservation row, a
settle transition, a release path, and a sweeper for reservations whose work
vanished. Charging at completion means an overshoot of at most one operation per
concurrent slot — bounded by agent concurrency and in-flight grades — and a provider
failure costs the learner nothing.

**Why elapsed-time rollover.** Every debit begins with: if the period has elapsed,
advance it and zero the usage. Self-healing, and **no job exists that can fail** — a
scheduled task that resets balances fails silently, because nobody notices credit
they did not try to spend.

**Why exhaustion needs no new state.** The sampling table takes `p(L4) = 0`, so
serving falls to level 3 or below — which is exactly the supply-shortfall path
already built in phase 5. Nothing is punished, strength keeps advancing, and the only
thing that pauses is the top rung.

**Deletion order**, and three steps carry a reason that is not obvious:

```text
1  revoke every refresh family, bump the token version
2  cancel non-terminal assistant Runs       ← inline work must not outlive its owner
3  delete assistant threads, runs, checkpoints
4  delete learning records
5  delete credit ledger and plan
6  delete jobs owned solely by this requester
   leave shared jobs; delete only this requester's interest   ← others are still reading
7  delete deck membership, then references pointing AT this owner's nodes, then nodes
                                             ← a dangling edge in someone else's tree
8  delete external identities, then the user
```

## Related Code Files

**Create**

- `apps/api/pycil/account/credit.py` — balance, the lazy roll, the debit
- `apps/api/pycil/account/plans.py` — the two tiers and their limits

**Modify**

- `apps/api/pycil/account_lifecycle/` → `apps/api/pycil/account/` (flat, `A2`)
- its deletion service — the eight steps, and remove the reference to the table phase 1
  dropped
- its export service — add credit and plan; keep dictionary content out
- the learning answer path — check balance at submit, debit at completion
- the agent run path — the same
- the sampling call — `p(L4) = 0` when the balance is exhausted
- the generation quota — per-plan daily limits

## Implementation Steps

1. Write `plans.py`: the two tiers, their grants, and their limits. Grants are
   `uncalibrated` — named constants with the measurement recorded, not invented
   numbers.
2. Write `credit.py`: `balance()`, the lazy roll inside every debit, and `debit()`
   under the unique key.
3. Wire the submit-time balance check into level-4 grading and into agent run
   creation. Zero balance is a typed refusal, not an error.
4. Wire the completion-time debit into the grade settle and the run finish. A failed
   grade debits nothing.
5. Wire exhaustion into the sampler: zero balance means `p(L4) = 0`, which the phase-5
   table already handles as a supply shortfall.
6. Move per-day generation limits into the plan, keeping them a rate limit rather than
   an economic one — paying must not remove a safety bound.
7. Rewrite deletion as the eight steps, with the shared-job distinction explicit.
8. Extend export with plan and credit; assert dictionary content stays out.
9. Verify the abort-on-forgotten-table property by adding a table and **not** adding
   its deletion step — the deletion must fail. That is the test.

## Todo

- [ ] `plans.py` with two tiers, grants marked `uncalibrated`
- [ ] `credit.py`: balance, lazy roll, unique-keyed debit
- [ ] Submit-time balance check on grading and runs
- [ ] Completion-time debit; a failure debits nothing
- [ ] Exhaustion sets `p(L4) = 0`
- [ ] Per-plan generation limits
- [ ] Deletion rewritten as nine steps
- [ ] Export includes plan and credit, excludes dictionary content
- [ ] Abort-on-forgotten-table proven by a test
- [ ] `account.md` §9 covered by named tests

## Success Criteria

- [ ] An email change keeps one account and one memory state
- [ ] A debit applies once under retried settlement
- [ ] A positive balance is required at submit; the debit lands at completion
- [ ] A failed grade debits nothing
- [ ] The period resets on the first debit after it elapses, with no job
- [ ] Exhausted credit serves a lower depth and grades it `Good`
- [ ] Exhausted credit does not lapse a sense
- [ ] An exhausted agent returns a refusal; learning is unaffected
- [ ] Export returns owner-scoped records and no dictionary content
- [ ] Export is available on every plan
- [ ] Deletion cancels non-terminal Runs first
- [ ] Deletion aborts loudly when a referencing table is forgotten
- [ ] Deletion leaves shared jobs intact, removing only this requester's interest
- [ ] Deletion removes references pointing at the deleted owner's nodes
- [ ] Deletion leaves the dictionary intact
- [ ] `account.md` §9 fully covered by named tests

## Risk Assessment

**The three grant values are guesses and will be visibly wrong.** Signal: a learner
exhausts a month of credit in a day, or never approaches the limit. Response: they
are `uncalibrated` by decision (`P12`), and the measurement that settles them —
token cost per grade, per turn, and the rubric grader's false-negative rate — is unavailable
because observability was dropped. Ship the shape, revisit with data.

**Charging at completion allows a bounded overshoot.** Deliberate. Signal: a learner
slightly exceeding their allowance. Response: accepted in exchange for no state
machine on the ledger; the bound is concurrency, which is small.

**Deletion order is the highest-consequence code in this phase.** A missed table
either aborts the delete (recoverable, and the property being bought) or orphans
rows (silent). Signal: step 9's test is what surfaces it. Response: that test adds a
table and omits its step, asserting the failure — an unusual test worth writing
because it verifies a property rather than a behaviour.

**Cancelling Runs before deleting their thread is easy to reorder.** Inline work
may reach another yield point after its owner is gone. Signal: a foreign-key violation,
or a successful write to a deleted owner's row. Response: cancellation precedes deletion, and
the order is a named test.
