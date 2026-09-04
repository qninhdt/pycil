# modules/account

Owns the user row, the plan, the credit ledger, export, and deletion order.
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

| LLM work | Reusable? | Charged |
|---|---|---|
| Generating a word — one call, forever | **yes**, every future learner | **no** |
| Generating a question — one type only | **yes**, shared pool | **no** |
| Grading levels 1–3 | no model at all | **no** |
| **Grading level 4** — the learner's own text | **no** | **credit** |
| **An agent turn** — this learner's thread and tools | **no** | **credit** |

The consequence is a healthy asymmetry: a free learner is **nearly free to serve**
(deterministic grading costs a database write) **and is a source of data** — every
word they generate enters the shared dictionary. Free is not a cost to absorb; it
is the supply side.

## 3. Two tiers and a top-up

`P2`. Two **feature** tiers, because there are not enough separately expensive
features to justify a third. But credit is a **consumable** and usage varies
widely, so a heavy learner needs a way to buy more without waiting for a period to
roll.

```text
Free   ·   Pro   ·   credit top-up pack
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
credit per period           small           large
  → L4 grading
  → agent turns
───────────────────────────────────────────────────────
analytics history window    recent          all-time
word generations per day    lower           higher
agent concurrency           1               2
```

Four reasons this shape and not another:

**The switching cost is the library plus the memory state, so neither is capped**
(`P3`). Capping library size attacks the exact mechanism that retains a learner;
capping reviews kills the habit, and habit *is* retention. A free learner who
never spends a credit is still a learner who would lose something by leaving.

**Studying a whole folder including nested subtree is free** (`P4`). The cost is
identical to studying one deck — the same indexed top-K (`D6`). Gating it would
make a free learner avoid building a tree, and the tree is the structure that holds
them. This is the clearest case where the obvious paid feature is the wrong one.

**Credit gates exactly two things and nothing else** (`P5`). One mechanism rather
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

## 4. Credit

One pool, denominated in **token work**, displayed with a human estimate (`P6`):

```text
1,240 credits    ≈ 120 writing checks  or  ≈ 50 agent conversations
```

Two separate allowances would read better on a pricing page and behave worse: an
unused agent allowance should become writing checks. One pool also means a future
feature that costs credit needs no new meter.

Denominating in currency is rejected — a provider reprices and every plan is wrong.
Token work is the unit the cost is actually incurred in.

### Schema

```text
user_credits
├── user_id          PK
├── plan             free | pro
├── period_start     the mark of the current period
├── period_used      reset lazily on rollover
└── topup_balance    purchased; does NOT expire with the period

credit_debits
├── id · user_id · kind · reference_id · amount · created_at
└── UNIQUE (kind, reference_id)          ← idempotency (P8)
```

`kind` is `grade_l4` or `agent_turn`; `reference_id` is the response id or the run
id.

```text
balance = grant(plan) - period_used + topup_balance
```

### Rollover is elapsed time, not a job

`P9`. Every debit begins with: if the period has elapsed, advance `period_start`
and zero `period_used`.

Lazy, self-healing, and **no job exists that can fail.** A scheduled task that
resets balances is a scheduled task whose failure is a billing incident — and it
fails silently, because nobody notices credit they did not try to spend.

### Charge at completion, not by reservation

`P7`. Reserve-settle-release needs a state machine on the ledger: a reservation
row, a settle transition, a release path, and a sweeper for reservations whose work
vanished.

Instead: **check a positive balance at submit, debit the actual amount at
completion.**

The overshoot is at most **one operation per concurrent slot** — bounded by agent
concurrency (1 or 2) and by however many grades a learner can have in flight. In
exchange there is no state machine, and a provider failure costs the learner
nothing because the debit never happened.

`UNIQUE (kind, reference_id)` is what makes a retried settle safe: the effect is an
**increment**, so it is the one consumer in this design needing an explicit dedup
key (`F7`). The index sits on the domain table, beside the data it protects.

### Running out degrades along a path that already exists

`P10`, and this is the part worth getting right.

Exhausting credit needs **no new state**. The sampling table (`B6`) drops level 4 to
zero probability, so serving falls to level 3 or below — which is exactly the
supply-shortfall path (`B7`): a correct answer still earns `Good`, depth simply does
not advance.

```text
credit exhausted
  → p(L4) = 0
  → serve at depth 3 or lower
  → correct answer: Good on strength, depth unchanged
  → the learner is told: "writing checks paused"
```

Nothing is punished, nothing breaks, and strength keeps advancing. The only thing
that pauses is the top rung — which is also the honest description of what was
bought.

The agent, out of credit, returns a typed refusal. Learning is unaffected.

### Three values await measurement

`P12`. Pro price, free grant, Pro grant are **`uncalibrated`**.

They need: the measured token cost of one level-4 grade, of one agent turn, and the
**rubric's false-negative rate** — that last one because a wrongly failed answer is
credit spent on a grade that has to be redone, and it also governs how rare level 4
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
2  disconnect the realtime session          best-effort, logged on failure
3  cancel non-terminal agent Runs           a running Run must not outlive its owner
4  delete agent threads, runs, checkpoints
5  delete learning records: responses, review log, learner-sense state,
   settings, session summaries
6  delete credit ledger and plan
7  delete jobs owned solely by this requester
   leave shared jobs alone; delete only this requester's interests
8  delete deck membership, then references pointing at this owner's nodes,
   then nodes
9  delete external identities, then the user
```

Three steps carry a reason that is not obvious:

- **Step 3 precedes deletion.** A Run holding a lease and writing on a fence will
  write after its owner is gone; cancelling first is what makes step 4 final.
- **Step 7 distinguishes shared from owned.** A word-generation job may have other
  authorized readers. Deleting the job would break their subscription; deleting
  only *this* requester's interest is correct. A job with **no** remaining
  interest is reclaimed by ordinary retention, not by deletion.
- **Step 8 removes references *pointing at* this owner** before the nodes. A
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
- Credit debited exactly once per operation, under retry.
- The period resets without a scheduled job.
- Exhausted credit degrades; it does not error and does not punish.
- Word generation never charged.

## 9. Invariants for the checklist

```text
an email change keeps one account and one memory state
two providers with the same subject are two identities
a debit is applied once under retried settlement
a positive balance is required at submit; the debit lands at completion
a failed grade debits nothing
the period resets on the first debit after it elapses, with no job
exhausted credit serves a lower depth and grades it Good
exhausted credit does not lapse a sense
an exhausted agent returns a refusal and learning is unaffected
export returns owner-scoped records and no dictionary content
export is available on every plan
deletion cancels non-terminal Runs first
deletion aborts loudly when a referencing table is forgotten
deletion leaves shared jobs intact and removes only this requester's interest
deletion removes references pointing at the deleted owner's nodes
deletion leaves the dictionary intact
a deleted user's realtime session is disconnected
```
