---
phase: 7
title: "Hierarchy"
status: pending
priority: P1
effort: "3-4d"
dependencies: [1]
---

# Phase 7: Hierarchy

## Overview

Collapse three encodings of the readability rule into one set-based query, and
collapse four duplicated analytics pairs into one route per metric with an optional
scope. Both are correctness work wearing the clothes of a cleanup.

## Requirements

**Functional**

- **One** readability implementation (`D3`) serving single-node authorization, batch
  deck authorization, and breadcrumb resolution.
- Breadcrumb stops at the first unreadable hop; private and missing are
  indistinguishable.
- A reference authorizes its target **independently** of its own container (`D4`) —
  a published folder never launders access to a private target.
- A revoked target keeps its node and says so; it does not render as an empty deck.
- `structural_generation` fences the subtree cache: generation **in the key**, bump
  and mutation in one transaction, eviction after commit, re-read after resolution
  (`D5`).
- Exact top-K in the database — at most `2K` rows, the application sorts nothing
  (`D6`).
- One route per metric with an **optional node scope** (`D7`); absent scope means the
  whole account, expressed as the same query without a scope filter.

**Non-functional**

- Redis unavailable may cost latency and never changes a committed outcome.
- The answer write stays constant-cost and independent of collection size.

## Architecture

Three encodings exist today, and each carries a comment acknowledging the others: a
per-hop Python walk with early exit, the same rule as one recursive query, and a
third inline forward pass with its own inherited-visibility array. Three encodings of
one authorization predicate is three places to over-grant, and they drift because
each looks correct in isolation.

```text
                    ┌─────────────────────────┐
single-node    ─────►                         │
batch decks    ─────►  one set-based query    │
breadcrumb     ─────►                         │
                    └─────────────────────────┘
```

The set-based version is the survivor. The Python walks exist because they return
whole node rows — so the consolidation is: the query returns ids plus the readability
verdict, and a caller needing rows fetches them by id. That is one extra
primary-key fetch on a path that currently walks the tree in Python.

**Analytics.** Four metrics — totals, weakest, distribution, history — each currently
having a folder-scoped and an account-scoped implementation. Two of the four already
parameterise scope in one function, which is the proof the split is unnecessary. The
other two are duplicated pairs whose docstrings explain that they must agree by hand
on what "learned" means — and they did not.

With `status = scheduled` from phase 5 as the single predicate, and the account scope
expressed as the same query with no scope filter, there is nothing left to disagree.

## Related Code Files

**Modify**

- `apps/api/pycil/hierarchy/` — flatten to `models/service/router/schemas` (`A2`)
- the access module — one set-based readability query, returning ids and verdicts
- the subtree module — becomes a caller of that query rather than a second copy
- the reads module — delete the third inline pass; breadcrumb calls the one query
- the stats module — collapse the two duplicated pairs into scope-parameterised
  functions
- the router — four analytics routes with an optional `nodeId`, replacing nine

**Delete**

- the per-hop Python walk and its ancestry helper
- the inline forward pass with its inherited-visibility array
- five of the nine analytics routes

## Implementation Steps

1. Extend the set-based query to return what all three callers need: node id,
   readability verdict, and depth for ordering.
2. Convert single-node authorization to it; a caller needing the row fetches by id.
3. Convert breadcrumb to it, preserving the stop-at-first-unreadable-hop rule — a
   path with a hole leaks the existence of what it skipped.
4. Delete both Python walks.
5. Verify the reference rule explicitly: a published folder containing a reference to
   a private deck exposes nothing. This is the laundering path and it needs its own
   test.
6. Collapse the two duplicated analytics pairs into scope-parameterised functions,
   with `None` scope meaning the whole tracked set inside SQL — the pattern two of
   the four metrics already use.
7. Reduce nine routes to four with an optional `nodeId`.
8. Confirm the top-K path returns at most `2K` rows and that the application performs
   no sort.
9. Verify the generation fence end to end: bump and mutation in one transaction,
   eviction after commit, and a stale generation unable to serve a cached subtree.

## Todo

- [ ] One set-based readability query serving all three callers
- [ ] Both Python walks deleted
- [ ] Breadcrumb stops at the first unreadable hop
- [ ] Reference-through-published-folder test
- [ ] Analytics pairs collapsed
- [ ] Nine routes reduced to four with an optional scope
- [ ] Top-K verified: `2K` rows, no application sort
- [ ] Generation fence verified end to end
- [ ] `hierarchy.md` §9 covered by named tests

## Success Criteria

- [ ] A private node and a missing node are indistinguishable
- [ ] A published folder does not expose a reference's private target
- [ ] A revoked target renders as revoked, not as empty
- [ ] Breadcrumb stops at the first unreadable hop
- [ ] A cycle is rejected on write; read traversal terminates on a repeat
- [ ] Depth beyond the cap is rejected
- [ ] One readability query serves single-node, batch, and breadcrumb
- [ ] A structural write bumps the node, its ancestors, and referencing ancestors
- [ ] A stale generation cannot serve a cached subtree
- [ ] Redis down: the mutation commits and reads resolve
- [ ] Moving a deck preserves every learner-sense record
- [ ] A sense in two decks is scheduled once
- [ ] Top-K returns at most `2K` rows; the application sorts nothing
- [ ] The same metric over a folder and over the account uses one predicate
- [ ] `hierarchy.md` §9 fully covered by named tests

## Risk Assessment

**Consolidating an authorization predicate is where an over-grant is introduced.**
Signal: a test that should deny passes. Response: the reference-laundering case is
the highest-risk one and gets its own named test, because it is the only path where
two independent authorizations must both hold and the tempting implementation checks
one.

**The set-based query cannot return node rows, so a caller changes shape.** Signal:
an extra query on a hot path. Response: it is one primary-key fetch replacing a
Python tree walk — strictly fewer round trips, not more. If a caller genuinely needs
rows for a whole subtree, that is the flattened-materialisation escalation `D6`
names, and it comes after a measurement rather than before.

**Collapsing nine routes to four is a wire change.** Pre-production with no external
consumer, and the client already chose between them with a conditional. Signal: the
web phase cannot express a call. Response: phase 10 is downstream precisely so a
route change is still cheap.

**"Learned" changes meaning here.** It is phase 5's decision landing in the readers.
Signal: a number the learner sees changes. Response: intended — two numbers for one
learner was the defect.
