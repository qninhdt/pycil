---
phase: 6
title: "Content"
status: pending
priority: P1
effort: "3-4d"
dependencies: [5]
---

# Phase 6: Content

## Overview

Fix the dictionary library's published contract so the consumer stops rebuilding
what the library already knows, then close the two supply questions the previous
design answered by accident. `lexi-ai` is a sub-project — edited directly, no PR,
pin bumped after its own suite passes.

## Requirements

**Functional**

- The contract **pins identity types** (`C4`): one logical id, one type, no cast at
  the boundary and no runtime handler wrapping the cast.
- `PresentedQuestion` **carries the render discriminator** (`C4`) — the library
  already names its shapes; the consumer must stop deriving it from a type ladder.
- The contract publishes **`word_id_for(sense_id)`** (`C5`).
- Retrieval never generates (`C3`); supply is requested ahead of need.
- A type change at one level is **not** a fallback; a level drop is, and is recorded.
- Answer safety by **per-variant field allowlist** (`C6`).
- Both open questions closed **deliberately**:
  1. the per-demand item count is honoured or removed from the contract;
  2. cross-session item repetition is decided.

**Non-functional**

- Pycil writes no dictionary table and joins across no boundary.
- The pin moves to a commit whose own suite passes (`N10`).

## Architecture

The boundary rule is unchanged: Pycil stores a sense id as a plain integer with no
foreign key. A leak is not an import — it is either Pycil knowing how the library is
implemented, or the library knowing Pycil exists.

Three fixes, all on the library side:

```text
before                                    after
PresentedQuestion.question_id: str        int, pinned
PresentedQuestion.sense_id:    str        int, pinned
PrepareDemand.sense_id:        str        int, pinned
  → consumer casts at 6+ sites,             → no cast
    wrapped in a runtime handler

render shape derived by isinstance ladder → PresentedQuestion.render_kind
  → a second copy that drifts;               → one field read
    a new shape is a runtime failure          a new shape is a type error

no way to get the owning word             → word_id_for(sense_id)
  → build a whole flashcard to read
    one foreign key
```

Keeping the **wire** name distinct from the library's internal type stays
deliberate: it lets the library refactor without a wire break. So the fix is for the
contract to *carry* a discriminator, not for the consumer to adopt the internal name.

**The two open questions**, and why they are decisions rather than defects:

*Item count.* The demand carries a count and the producer ignores it, so a request
for three yields one. A contract field the producer ignores is worse than an absent
one — the next reader takes it for a promise. Honouring it needs a variation source
per type: several examples for a cloze, a wider distractor pool for a choice item.
The productive type has none short of a model call.

*Cross-session repetition.* The exclusion set is session-scoped, so a new session
starts empty and previously served items recur. Re-recognition is still review — but
it means an assessment can be memorised rather than answered. A durable exclusion set
grows without bound. Real cost either way.

## Related Code Files

**Modify in `../lexi-ai`**

- the contracts module — pin identity types, add `render_kind`
- the reader protocol and its implementation — publish `word_id_for`
- the question plugins — honour or drop the per-demand count, per the decision
- its own suite for each change

**Modify in `pycil`**

- `apps/api/pyproject.toml` — bump the pin (the gap is one commit)
- `apps/api/pycil/ports/lexi.py` — drop the two uncalled protocol members; the
  remaining ones lose their casts
- `apps/api/pycil/content/` — flatten (`A2`); delete the caster and the runtime
  handler that wrapped it
- the question delivery path — `render_kind` replaces the isinstance ladder
- the supply demand builder — the count decision, and the work key stays
  `(session, round)`
- the worker's supply job — `word_id_for` replaces building a flashcard

**Keep**

- `apps/api/tests/test_v1_contract.py` and
  `apps/api/tests/learning/test_delivery_payload_leak.py` — the answer-safety pair

## Implementation Steps

1. Decide the two open questions. Write the decision into
   `../modules/content.md` §10 — replacing the open item, not appending to it.
2. In `lexi-ai`: pin the identity types across the contracts module. Run its suite.
3. In `lexi-ai`: add `render_kind` to the presented question, sourced from the type
   registry that already names it. Run its suite.
4. In `lexi-ai`: publish `word_id_for` on the reader. Run its suite.
5. In `lexi-ai`: implement the count decision — either a variation source per type,
   or remove the field from the contract. Run its suite.
6. Bump the pin in `pyproject.toml`.
7. Delete Pycil's casts and the runtime handler that wrapped them.
8. Replace the isinstance ladder with a `render_kind` read.
9. Replace the flashcard-for-a-foreign-key call with `word_id_for`.
10. Drop the two uncalled protocol members.
11. Verify the answer-safety allowlist still holds against the changed presentation
    types — a new field on a variant is exactly what the allowlist exists to catch.

## Todo

- [ ] Decide and record the two open questions
- [ ] `lexi-ai`: identity types pinned
- [ ] `lexi-ai`: `render_kind` on the presented question
- [ ] `lexi-ai`: `word_id_for` published
- [ ] `lexi-ai`: count honoured or removed
- [ ] `lexi-ai` suite green
- [ ] Pin bumped
- [ ] Pycil casts and their handler deleted
- [ ] `render_kind` replaces the isinstance ladder
- [ ] `word_id_for` replaces the flashcard call
- [ ] Two uncalled protocol members dropped
- [ ] Answer-safety allowlist re-verified
- [ ] `content.md` §9 covered by named tests

## Success Criteria

- [ ] No Pycil query touches a dictionary table
- [ ] No cast of a dictionary identifier anywhere in Pycil
- [ ] No isinstance ladder deriving a render shape
- [ ] Retrieval never triggers generation
- [ ] Empty supply returns a state, not an error and not a stalled request
- [ ] A type change at one level is not recorded as a fallback; a level drop is
- [ ] Supply for one round is generated once under concurrent requests
- [ ] The same question inserted twice yields one row
- [ ] A client-supplied work key is rejected
- [ ] No answer-shaped field appears in any presentation schema
- [ ] A submission carrying a question payload is ignored
- [ ] `../modules/content.md` §10 contains decisions, not open questions
- [ ] `content.md` §9 fully covered by named tests

## Risk Assessment

**Editing the sub-project directly means no review boundary.** Signal: the pin bumps
to a commit whose suite was not run. Response: step ordering — its suite runs after
each change, before the bump. The gap is one commit, so a bad bump is cheap to
correct, which is the actual mitigation.

**Pinning identity types is a breaking change to a published contract.** Everything
consuming it is in these two repositories, so the blast radius is known. Signal: a
type error at the boundary, which is the point — it is currently a runtime handler.

**Honouring the item count could balloon.** Each type needs a variation source, and
the productive type has none. Signal: the change reaching for a model call to
generate variation. Response: if that is where it lands, remove the field from the
contract instead — an honest absence beats an expensive promise.

**Cross-session repetition has no cheap answer.** Both options have a real cost.
Response: decide it, record it, and accept the cost named. Leaving it undecided is
how it became a defect the first time.
