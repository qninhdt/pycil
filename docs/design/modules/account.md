# modules/account

Owns the user row, the plan, usage entitlements, export, and deletion order.
Decisions `P1`–`P12`, `H7`, `O11`.

Does not own authentication (`auth` does) or any per-domain rule — deletion calls
each module's ordering, it does not reimplement it.

## 1. The user

```text
users
├── id
├── display_name · avatar_url        from the identity provider, refreshed at login
├── token_version                    bumped to revoke (H6)
└── created_at

external_identities
├── (issuer, subject)  UNIQUE        the identity key (H7)
├── user_id
└── email                            observed, never the key
```

Email is **stored, never keyed on** (`H7`). The provider documents that email
changes and that the subject is stable `[R13]`; keying on email means an email
change creates a second account and abandons the learner's memory state — the one
asset in this product that cannot be regenerated.

A second provider later is additional rows in `external_identities`, not a schema
change.

## 2. The economic rule

`P1`. One sentence, and everything else in this file follows from it:

> **Charge for what cannot be reused. Give away what enriches the commons.**

| LLM work | Reusable? | Metered Against Allowance |
|---|---|---|
| Generating a word — one call, forever | **yes**, every future learner | **no** |
| Generating a question — one type only | **yes**, shared pool | **no** |
| Grading levels 1–3 | no model at all | **no** |
| **Grading level 4** — the learner's own text | **no** | **yes (metered usage)** |
| **An agent turn** — this learner's thread and tools | **no** | **yes (metered usage)** |

The consequence is a healthy asymmetry: a free learner is **nearly free to serve**
(deterministic grading costs a database write) **and is a source of data** — every
word they generate enters the shared dictionary. Free is not a cost to absorb; it
is the supply side.

## 3. Two tiers

`P2`. Two **feature** tiers, because there are not enough separately expensive
features to justify a third. Plans grant access to features and a monthly usage allowance.

```text
Free   ·   Pro
```

A third tier, if it ever exists, is a **larger bucket** — not new features.

### What each tier is

```text
                            Free            Pro
library size                unlimited       unlimited
nesting depth               to the cap      to the cap
study a folder + subtree    full            full
reviews per day             unlimited       unlimited
grading L0-L3               unlimited       unlimited
publish a link              full            full
data export                 full            full
session shape settings      full            full
───────────────────────────────────────────────────────
monthly allowance units     small           large
  → L4 grading
  → agent turns
───────────────────────────────────────────────────────
analytics history window    recent          all-time
word generations per day    lower           higher
active assistant turns      1               5
```

Four reasons this shape and not another:

**The switching cost is the library plus the memory state, so neither is capped**
(`P3`). Capping library size attacks the exact mechanism that retains a learner;
capping reviews kills the habit, and habit *is* retention. A free learner who
never uses metered features is still a learner who would lose something by leaving.

**Studying a whole folder including nested subtree is free** (`P4`). The cost is
identical to studying one deck — the same indexed top-K (`D6`). Gating it would
make a free learner avoid building a tree, and the tree is the structure that holds
them. This is the clearest case where the obvious paid feature is the wrong one.

**Usage metering gates exactly two things and nothing else** (`P5`). One mechanism rather
than a feature flag beside a meter. Almost everything else costs nothing to serve,
so gating it would be pricing for its own sake.

**The depth ladder is the paywall, and it is honest.** A free learner reaches
`depth_level` 3 — cued recall, typed answers — on deterministic grading alone.
Level 4 is productive use, the one thing needing a rubric. Stage names already
render from `depth_level` (`B13`), so **the locked rung is visible in the product**
without a single upsell surface: the learner can see what they have not proven yet.

Export is free on every plan, and that is a position, not a concession: a product
holding a learner's memory state hostage has a retention strategy rather than a
value proposition.

## 4. Usage Entitlements & Metering

One allowance pool, denominated in **internal usage units**, displayed with quota and utilization (`P6`):

```text
1,240 / 10,000 monthly allowance units remaining (renews Nov 1)
```

Two separate allowances would read better on a pricing page and behave worse: an
unused agent allowance should become writing checks. One pool also means a future
feature that consumes allowance needs no new meter.

Denominating in currency is rejected — internal units are an operational metering mechanism, not money.
Usage units normalize provider token costs and rubric evaluations without introducing wallet semantics.

### Schema

```text
account_plans
├── user_id          PK
├── plan_key         free | pro
├── period_anchor    the anchor timestamp for calendar monthly periods
├── created_at
└── updated_at

usage_periods
├── id               PK (UUID)
├── user_id          FK -> users.id
├── plan_key         free | pro
├── period_start     [start, end)
├── period_end
├── allowance_units  internal units granted for the period
├── used_units       units consumed so far
├── created_at
└── updated_at

usage_events
├── id · period_id · event_key · feature_key · units · occurred_at · details · created_at
└── UNIQUE (period_id, event_key)       ← idempotency (P8)
```

`feature_key` is `level4_grading` or `assistant`; `event_key` is the response id or the turn settlement key.

```text
remaining_units = allowance_units - used_units
```

### Rollover is elapsed time, not a job

`P9`. Every usage check and recording begins with: if the period has elapsed, advance to the current
calendar month usage period.

Lazy, self-healing, and **no job exists that can fail.** A scheduled task that
resets balances is a scheduled task whose failure is an incident — and it
fails silently, because nobody notices allowance they did not try to consume.

### Record at completion, not by reservation

`P7`. Reserve-settle-release needs a state machine on the ledger: a reservation
row, a settle transition, a release path, and a sweeper for reservations whose work
vanished.

Instead: **check remaining allowance at submit, record actual usage at
completion.**

The overshoot is at most **one operation per active slot** — one Assistant turn
for Free, five for Pro, plus grading already in flight. A same-thread lease blocks
overlapping turns, HITL pauses release their slot, and ten starts per minute bound
start/cancel spam. Failed provider executions remain free; a client disconnect
settles usage from completed model calls and ignores only the incomplete call.

The billing event's server-generated `event_key` makes retries within one admitted
execution idempotent. It is a settlement key only; it does not determine whether an
AG-UI run ID has executed. Process crashes remain best effort, without an execution
ledger or recovery worker.

### Running out degrades along a path that already exists

`P10`, and this is the part worth getting right.

Exhausting the usage quota needs **no new state**. The sampling table (`B6`) drops level 4 to
zero probability, so serving falls to level 3 or below — which is exactly the
supply-shortfall path (`B7`): a correct answer still earns `Good`, depth simply does
not advance.

```text
usage quota exhausted
  → p(L4) = 0
  → serve at depth 3 or lower
  → correct answer: Good on strength, depth unchanged
  → the learner is told: "writing checks paused"
```

Nothing is punished, nothing breaks, and strength keeps advancing. The only thing
that pauses is the top rung — which is also the honest description of what was
bought.

The agent, out of allowance, returns a typed refusal (`usage_quota_exhausted`). Learning is unaffected.

### Three values await measurement

`P12`. Pro price, free allowance, Pro allowance are **`uncalibrated`**.

They need: the measured token cost of one level-4 grade, of one agent turn, and the
**rubric's false-negative rate** — that last one because a wrongly failed answer is
usage spent on a grade that has to be redone, and it also governs how rare level 4
should be (`B6`).

Observability was deliberately dropped (`O7`), so these stay `judgment` until it
returns. Per R5 the constraint is recorded rather than a number invented.

## 5. Word generation is metered, not charged

`P11`. It is the largest single LLM cost and it is **not** charged, because it
enters the shared dictionary.

Abuse control instead, and it is a **rate limit, not an economic one**: generations
per day by plan, in-flight per learner, in-flight globally. Conflating the two
produces a product where paying removes a safety bound.

Shared work joining is itself the strongest control here: a hundred learners asking
for one word produce **one** job (`C2`), so the cost ceiling is the size of the
dictionary — not the number of requests.

## 6. Export

Every plan, complete, unconditional (`P3`).

Returns the learner's **own** records: identity, the node tree, deck membership as
sense ids, learner-sense state, review history, session summaries, agent threads.

It returns **no dictionary content**. Definitions are not the learner's data — they
were contributed to the commons and belong to it. Sense ids are exported so the
data is re-importable, but the entries themselves are not copied out.

Bounded by construction: it is a set of owner-scoped reads, not a crawl.

## 7. Deletion

Ordered by hand, with `NO ACTION` foreign keys (`O11`).

The reason is structural: two schemas share one database and the cross-schema
reference is **a plain integer with no constraint** (`A5`), so a cascade cannot
traverse it. Declaring cascades would be false safety — the boundary a cascade
cannot cross is exactly the boundary that matters.

**A forgotten table aborts the deletion loudly.** That is the property being
bought, and it is an invariant on the checklist rather than a script to maintain.

```text
1  revoke every refresh family and bump the token version
2  cancel non-terminal assistant Runs       inline work must not outlive its owner
3  delete assistant threads, runs, checkpoints
4  delete learning records: responses, review log, learner-sense state,
   settings, session summaries
5  delete usage periods, usage events, and plan
6  delete jobs owned solely by this requester
   leave shared jobs alone; delete only this requester's interests
7  delete deck membership, then references pointing at this owner's nodes,
   then nodes
8  delete external identities, then the user
```

Three steps carry a reason that is not obvious:

- **Run cancellation precedes deletion.** Inline execution observes the
  cancellation marker before its next write, so work cannot continue after its
  owner has gone.
- **Step 6 distinguishes shared from owned.** A word-generation job may have other
  authorized readers. Deleting the job would break their polling access; deleting
  only *this* requester's interest is correct. A job with **no** remaining
  interest is reclaimed by ordinary retention, not by deletion.
- **Step 7 removes references *pointing at* this owner** before the nodes. A
  reference whose target row is gone has no meaning, and leaving it would leave a
  dangling edge in someone else's tree.

Deletion leaves the **shared dictionary untouched**. A generated word is not the
learner's data, and no other learner's library should break because someone left.

## 8. Capabilities that may not be cut

Per R4:

- Identity keyed on `(issuer, subject)`; email observed only.
- Export complete and free on every plan.
- Deletion aborts loudly on a table nobody remembered.
- Non-terminal Runs cancelled before their owner's data is removed.
- Shared work survives one participant's deletion; only their interest goes.
- Usage recorded exactly once per operation, under retry.
- The period rolls over without a scheduled job.
- Exhausted allowance degrades; it does not error and does not punish.
- Word generation never charged.

## 9. Invariants for the checklist

```text
an email change keeps one account and one memory state
two providers with the same subject are two identities
usage is recorded once under retried settlement
sufficient remaining allowance is required at submit; the usage lands at completion
a failed grade records no usage
the period rolls over on the first usage recording after it elapses, with no job
exhausted usage quota serves a lower depth and grades it Good
exhausted usage quota does not lapse a sense
an exhausted agent returns a refusal (usage_quota_exhausted) and learning is unaffected
export returns owner-scoped records and no dictionary content
export is available on every plan
deletion cancels non-terminal Runs first
deletion aborts loudly when a referencing table is forgotten
deletion leaves shared jobs intact and removes only this requester's interest
deletion removes references pointing at the deleted owner's nodes
deletion leaves the dictionary intact
a deleted user's non-terminal assistant Runs are cancelled before owned rows go
```
