# modules/learning

Owns sessions, the two axes, FSRS effects, and response records. Decisions
`B1`–`B13`.

Does not own question content (that is `content`), node authorization (that is
`hierarchy`), or the learner-sense table's home (that is `policy`, `A3`) — though
it is its only writer.

## 1. The root defect this replaces

Depth — how demanding a retrieval is — had **no durable home**. Only a per-answer
transaction table recorded a level, and a transaction table is not a learner
model. So depth evidence was pushed into the strength axis, and the symptoms
were:

- a supply shortfall recorded as a learner failure, with a UI component whose
  only job was to apologise for it;
- five stage names in the language of depth, computed from a strength value;
- one question per `(sense, level, type)` because depth was not treated as
  needing its own evidence;
- two questions collapsing into one memory update.

One cause. `B1` is the fix: two axes, each with its own state, each reading the
same answer.

## 2. Two axes

```text
answer
  ├─► WHEN — strength.  FSRS-4.5, published weights, binary.
  │     wrong   → Again
  │     correct → Good
  │     → stability, difficulty, next review time
  │
  └─► WHAT — depth.  A ladder with a streak.
        wrong                     → depth − 1 (floor 1), streak = 0
        correct, served == depth  → streak + 1; at 2 → depth + 1, streak = 0
        correct, served <  depth  → unchanged
```

The third row is what makes the split work, and it applies to **every**
below-depth serve — whether supply ran out or the sampler chose lower on purpose.
Correct recall *is* retrieval, so stability is earned and `Good` is right. It is
*not* evidence at the requested depth, so depth does not move. Nobody is punished
and nobody is wrongly rewarded (`B7`).

The rules are deliberately asymmetric: passing below depth is neutral, **failing**
below depth still retreats (`B8`). Evidence is asymmetric — failing an easier item
disproves the deeper claim, while passing one does not prove it.

Strength stays binary (`B3`). Hard means "the learner struggled", a subjective
report; using it to encode a supply fact inverts the meaning, and the published
weight vector does not carry the penalty term that a third grade needs.

## 3. State

On the learner-sense row (`policy`, since `content` and `hierarchy` read it):

| Field | Meaning |
|---|---|
| `stability`, `difficulty` | FSRS memory state |
| `next_review_at` | Derived from stability |
| `mastery` | Displayed strength: a saturating function of stability |
| `depth_level` | 0–4. **0 means never assessed** (`B4`) |
| `depth_streak` | Consecutive clean passes at the current depth (`B4`) |
| `status` | `new` or `scheduled` |
| `review_count`, `lapse_count` | Counters |

`status` is the lifecycle, and it is also the definition of "learned" (`B12`).
Two competing predicates over `review_count` and `mastery` were being rendered on
one screen, showing one learner two numbers. `scheduled` means "has entered FSRS
scheduling" — one source, derivable, no threshold.

Durable elsewhere: a review log (one row per graded answer, carrying the before
and after so weights can be refitted later, `B2`), response records, and a
presentation-only session summary so a recap survives the loss of session-local
state.

Session-local, in Redis: the admitted set, per-sense progress, the served-question
exclusion set, the current round. All of it disposable — a session that ends
mid-flight leaves only FSRS effects behind.

## 4. Difficulty scale

Five stages. Level 0 is exposure and never an assessment.

| Level | Demand | Answer visible? |
|---|---|---|
| 0 | Exposure — read it | n/a, ungraded |
| 1 | Direct recognition | yes |
| 2 | Contextual discrimination | yes, but lookup is insufficient |
| 3 | Cued recall | no, response tightly constrained |
| 4 | Productive use | no, response space open |

The scale measures **retrieval demand and response freedom**, not prompt length or
word rarity. A hard multiple-choice item is still level 1 or 2 because the answer
is visible; a simple typed recall is still level 3 because it must be retrieved.

## 5. Serving: one probability table keyed by depth

`serve_level` is **not** `depth_level` (`B6`). Two different questions were
collapsed into one variable:

- `depth_level` — "how deep has this learner proven they can go". An achievement:
  durable, remembered.
- `serve_level` — "how deep does *this* review ask". A tactic.

| `depth_level` | L1 | L2 | L3 | L4 |
|---:|---:|---:|---:|---:|
| 1 | 1.00 | — | — | — |
| 2 | 0.40 | 0.60 | — | — |
| 3 | 0.10 | 0.30 | 0.60 | — |
| 4 | — | 0.30 | 0.45 | **0.25** |

Only a serve **at** `depth_level` counts toward the streak, so depth climbs more
slowly but on real evidence. The `p(L4) = 0.25` row *is* the level-4 rate limit —
folding it into the table leaves one mechanism instead of two.

**These numbers are `uncalibrated`.** The measurement that settles them is the
level-4 rubric grader's false-negative rate; it governs how rare level 4 should
be. The defensible difference from what this replaces is not the numbers: the old
sampler drew from a memoryless function of strength, this one draws from a window
around a remembered achievement. Wrong parameters here are recoverable; the old
keying was wrong in kind.

### Why a window and not a monotonic ladder

Cross the table with question-type coverage:

| Level | Types available |
|---:|---|
| 1 | definition MCQ, contextual MCQ |
| 2 | contextual MCQ, cloze |
| 3 | cloze, use-in-sentence |
| 4 | **use-in-sentence only** |

Under `serve_level = depth_level`, a learner at depth 3 never sees a multiple
choice again, ever; at depth 4 there is one type forever. Three consequences:

1. **Grading cost never amortises.** Level 4 grades the learner's own text, so
   unlike the shared question pool it cannot be reused. In a mature schedule most
   reviews are of mature items, so most reviews would be a model call.
2. **Level-4 supply is one item with no variation source.** Prompt and rubric are
   templates; the learner meets a single prompt for the rest of that word's life.
3. **False negatives concentrate on the best-known words.** Deterministic formats
   have a zero false-grade rate; a rubric grader does not. Each false negative is
   a genuine lapse — stability cut, lapse counted, interval near the floor.

That third one is the same shape as the defect this design removes: the
highest-mastery learner punished most, cause moved from a thin pool to a mis-grade.

The window improves four things at once, so it is not a cost-for-quality trade:
varied retrieval practice beats repeating one format; grading cost drops to a
fraction of reviews; most reviews return to deterministic grading; and "diverse
questions" keeps meaning something for the most engaged learner — under the
monotonic rule, the longer someone used Pycil the *less* variety they would see,
inverting the selling point.

The argument for monotonic is real and recorded: for a vocabulary product,
production *is* the goal, so asking at production level forever asks the right
thing. False-negative accumulation outweighs it, and the window still keeps the
majority weight at or near depth.

## 6. New-sense entry

A never-assessed sense has `depth_level = 0` and `status = new`, and 0 is not a
row in the table. So its first assessment is **level 1 by definition, not
sampled**. That first graded answer sets `status = scheduled` and
`depth_level = 1` whichever way it goes; correct additionally sets the streak,
wrong records a lapse.

Exposure changes nothing durable — it only marks the sense exposed in
session-local state. So `depth_level = 0` never coexists with
`status = scheduled`, which is consistent with level 0 being ungraded.

The lapse floor is 1, never 0, because 0 now means "not yet in assessment" rather
than "weakest" (`B5`).

## 7. One question, one grade

`B9`. No checkpoints, no retry budget, no priority tiers, no disqualifier. One
answer produces exactly one review-log row.

But deleting the machinery must not delete the teaching. A wrong answer does two
separate things (`B10`):

1. **grades once** — Again, depth retreat, immediately and durably;
2. **returns the sense in a later round as an ungraded re-ask.**

The re-ask shows a different question (the exclusion set still applies), gives
right/wrong feedback, and writes **nothing**: no review log, no stability, no
depth. Exactly like an exposure.

Three rules complete it:

- Serve the re-ask at the level that was **failed**, not at the new lower depth.
  The point is repairing what just broke, and no depth rule applies to an ungraded
  item — so serving above current depth is not an inconsistency.
- **One ungraded re-ask per sense per session.** Bounds the loop with no retry
  budget parameter.
- Enforced by a graded-set in session state: once a sense is graded this session,
  every later encounter is ungraded. No durable table needed — the response record
  already carries a per-session idempotency key under a unique index, and if
  session state is gone the session has ended.

## 8. Session shape

A learner configures **two** numbers: how many unique senses to study, and how
many items before a break. Round count is **not** a setting; it follows (`B11`).

Graded answers per sense is invariably one. Total *items* varies because
exposures and re-asks are ungraded:

| Sense | Outcome | Items |
|---|---|---:|
| scheduled | right | 1 |
| scheduled | wrong | 2 |
| new | right | 2 |
| new | wrong | 3 |

```text
items  = admitted + new_among_them + failed
rounds = ceil(items / max_per_round)
```

At the defaults that is a **bounded** range with no long tail — which is what lets
the API name the round being entered and the client show real progress rather than
a guessed percentage.

Planning runs **once** per session: exact top-K in Postgres, due first, backfilled
with new, always reserving a floor of new senses even under a large due backlog
(`D6`). Session shape is the **learner's**, not the deck's.

Rounds survive as UI pagination — "that many items, take a break". They carry no
scheduling meaning, so a round boundary is a render decision.

### Ordering inside a round

Two hard constraints: a sense's exposure precedes its graded question, and a
re-ask lands in a later round than the failure it repairs. Otherwise **shuffle** —
same reason the window beat the ladder: interleaving beats homogeneous blocks.
Cheap, and it needs no priority tiers.

## 9. Walkthrough

Ten senses, cap of eight items. Round 1:

| # | Sense | depth | Sampled | Served | Answer | Strength | Depth |
|---:|---|---:|---|---|---|---|---|
| 1 | A | 4 | L3 | cloze | right | Good | 4 → 4, neutral |
| 2 | C | 2 | L2 | MCQ | **wrong** | Again, lapse | 2 → **1** |
| 3 | I | new | — | exposure | ungraded | — | — |
| 4 | B | 3 | L3 | cloze | right | Good | streak 2 → **depth 4** |
| 5 | E | 1 | L1 | MCQ | right | Good | streak 2 → **depth 2** |
| 6 | D | 4 | L4 | use-in-sentence | free text | Good | 4 → 4 |
| 7 | J | new | — | exposure | ungraded | — | — |
| 8 | F | 3 | L3 | **no supply** → L2 | right | Good | 3 → 3, depth-capped |

Cap reached, break announced. Round 2:

| # | Sense | Served | Answer | Strength | Depth |
|---:|---|---|---|---|---|
| 9 | I | L1, entry not sampled | right | Good | `new`→`scheduled`, **depth 1** |
| 10 | G | L1 (below depth 2) | right | Good | unchanged |
| 11 | H | L1 | **wrong** | Again | 1 → 1, floor |
| 12 | J | L1, entry | **wrong** | Again | `scheduled`, **depth 1** |
| 13 | C | L2, different item | right | **nothing** | unchanged |
| 14 | H | L1, different item | wrong | **nothing** | unchanged |
| 15 | J | L1, different item | right | **nothing** | unchanged |

Fifteen items: **ten graded, exactly one per admitted sense**, two exposures,
three ungraded re-asks. Then a durable summary and the recap.

D's free-text grade returns synchronously before the response is committed. A
provider timeout returns an error and leaves the item answerable; no pending
grade state appears in the session or recap.

## 10. Named consequence

A sense whose supply never reaches level 3 climbs in stability, reaches full
`mastery`, and sits at `depth_level` 2. Both facts are true. The UI shows the
depth-derived stage, so the learner is not told they are fluent. And the situation
becomes an operational fact worth acting on — senses depth-capped by supply —
instead of a silent mis-grade.

## 11. Capabilities that may not be cut

Per R4:

- FSRS arithmetic stays a pure function with no I/O, and its weight vector keeps
  every published index so it stays aligned with the reference implementation
  even where a term is unemitted.
- One memory update per sense per session, enforced durably. Two answers must
  not double-count.
- The answer key never reaches the client; the server re-fetches what it issued
  and grades that, so a submitted payload cannot carry its own answer.
- A free-text grade is synchronous and atomic; timeout writes no grading effect.
- An aborted answer reopens its delivery so the sense is not lost for the rest of
  the session.
- The write path for one answer stays a constant number of primary-key statements
  in one transaction, independent of collection size.

## 12. Invariants for the checklist

Named tests live in [../ops/testing.md](../ops/testing.md):

```text
one answer produces exactly one review-log row
a correct answer never produces Again under any supply condition
depth advances only on a clean pass at the served depth
depth retreats on a wrong answer at any level; floor 1
depth 0 never coexists with status = scheduled
an ungraded re-ask writes nothing: no log, no stability, no depth
at most one ungraded re-ask per sense per session
session completes with a grade still pending
the recap survives the loss of session-local state
stage name derives from depth; mastery derives from stability; independently assertable
```
