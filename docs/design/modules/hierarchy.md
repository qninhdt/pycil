# modules/hierarchy

Owns the node tree, readability, structural generation, and subtree scope.
Decisions `D1`–`D7`.

Does not own learning state (it *reads* the learner-sense row from `policy`, `A3`)
or dictionary content (`content` calls the library).

## 1. The node model

One table (`D1`):

| Type | Role | Children | Membership |
|---|---|---|---|
| `FOLDER` | Container | any node | — |
| `DECK` | Leaf | none | opaque sense ids |
| `REFERENCE` | Leaf | none | none — points at a deck |

`FOLDER` is the only type that contains. `parent_node_id` is the adjacency edge;
`target_node_id` is set **only** on a reference, enforced by a check constraint so
the shape cannot drift.

Parent edges are **same-owner only**. A reference is the one cross-owner edge
(`D4`).

Depth is **capped**. Not to hide complexity but to bound traversal: an
adjacency list with a recursive query answers every question this product asks, and
a cap is what makes the worst case knowable.

## 2. A node is a path, never an identity

`D2`, and it is the decision the rest of the module serves.

Progress identity is `(learner, sense)` — **global**. The same sense in three decks
is one memory. So a learner can reorganise their library freely and lose nothing,
which is the operation a card-based product punishes: there, moving a term between
sets means learning it twice.

Consequences:

- deck membership is a **set of sense ids**, not a set of learning records;
- deleting a deck does not delete progress;
- two decks containing one sense do not double-schedule it — planning works over a
  **distinct** sense set.

## 3. Readability

One rule, and **one implementation** (`D3`).

A node is readable when the viewer owns it, or the node itself is public, or it
sits under a public folder through an **uninterrupted same-owner ancestor chain**.
Writes are owner-only. A deleted ancestor hides the subtree beneath it.

Three encodings of this predicate is three places to over-grant, and they drift
silently because each looks right on its own. So there is exactly one set-based
query, and it serves:

```text
single-node authorization
batch deck authorization
breadcrumb resolution
```

Breadcrumb traversal **stops at the first unreadable hop** rather than skipping it —
a path with a hole is a path that leaks the existence of what it skipped.

Public means **link readability, not discovery** (`Q13`). A private node and a
missing node return the same response; distinguishing them leaks existence.

Publishing a folder is an explicit action and applies to current **and future**
descendants. Making something private again is not an approval-worthy action;
publishing is, because it is the direction that exposes.

### References and revoked targets

A reference points **live** at a deck, which is the feature a copy cannot give: the
target's owner edits, and every reference sees it.

When a target becomes private or is deleted, the reference **remains and says so**
(`D4`). It contributes no content. It does not render as an empty deck, because
that would be a lie — nothing is broken; someone changed their mind about sharing.

A containing folder's publication **never overrides** the target's own
authorization. Otherwise a reference would be a laundering path: point at
someone's private deck, publish the folder holding the reference, and the content
leaks. Each hop authorizes independently.

## 4. Structural generation

`D5`. The subtree-to-sense-set answer is cached, and the cache is **fenced by a
version** rather than invalidated by deletion.

```text
key:  node:<id>:senses:v<generation>[:viewer:<id>]
```

Because the generation is **in the key**, a stale fill can never mask newer
structure, and old generations become unreachable without relying on a delete
succeeding.

| Structural — bumps the generation | Not structural |
|---|---|
| create, move, soft-delete | answering a question |
| visibility or publication change | an FSRS update |
| add or remove a sense | a session starting |
| reference created, removed, or its target's access changing | — |

A structural write bumps every affected node, all of their ancestors, **and** the
ancestors of any reference targeting them — in **one** set-based statement, not a
loop per descendant.

Four rules that make the cache safe:

- the mutation and the bump are in the **same transaction**;
- the cache is evicted only **after** commit;
- the generation is **re-read** after resolution, and a result is published only if
  it is unchanged;
- Redis being unavailable may cost latency but **never** changes the outcome of a
  committed or rolled-back mutation.

Concurrency uses stable-order advisory locks then a re-read under lock. The locks
only reduce contention; correctness rests on the constraints.

## 5. Session scope and exact top-K

The canonical scope of a node is: the recursive **same-owner subtree**, plus the
distinct sense ids from its direct decks, plus the sense ids of independently
authorized live reference targets.

One relation and one cache feed **everything** — sessions, statistics, item lists,
weakest, distribution, history. A second implementation of "what senses are in
scope" is a second answer.

Selection is **exact top-K in the database** (`D6`):

```text
query top K due  and top K new           → at most 2K rows returned
the database filters the eligible set and applies ORDER BY … LIMIT K
the application never loads and sorts every candidate
```

Due order is exactly "lowest recall first, then most overdue", expressed as an
**order-preserving key** over the FSRS quantities rather than the recall formula
itself — so the formula is not duplicated in SQL where it could drift. New order is
stable by id.

Then the planner applies the new-word floor and backfills (`B11`).

No approximation, no hard cap on collection size, and no extra ranking index before
a measurement says one is needed. Exact ranking on an arbitrary dynamic score
without an order-compatible index does require evaluating the eligible set — that
is a property of the problem, and the target is one round trip with bounded
top-N selection, not a pretence that it is free.

If a measured target is missed, the **first** escalation is materialising a flat
node-to-sense relation — not closure tables, not a score cache, not approximate
retrieval.

## 6. Analytics: one route per metric, optional scope

`D7`. Four metrics — totals, weakest, level distribution, history — each with one
route taking an **optional node scope**. Absent scope means the whole account.

The previous shape had a folder route beside an account route for each metric,
which cost two implementations that had to **agree by hand** on what "learned" and
"mastered" mean. They did not: one required a review to have happened, the other
also accepted any nonzero strength, and both were rendered on one screen showing
one learner two numbers.

Two things fix it. "Learned" is `status = scheduled` (`B12`) — one predicate,
derivable, no threshold. And the account scope is the **same query with no scope
filter**, not a second function, so there is nothing left to disagree.

The client already chose between the two routes with a conditional, so collapsing
them costs nothing at the call site.

## 7. Complexity envelope

Stated as a target, not a promise about rows:

| Operation | Target |
|---|---|
| One-level listing, owner-scoped | one keyset query |
| Breadcrumb | one readability query |
| Single-node authorization | one readability query |
| Batch deck authorization | one readability query |
| Subtree → distinct sense set | zero queries on a cache hit; one on a miss |
| Structural mutation + invalidation | one affected-set query plus one update |
| Learner aggregate | one indexed range scan |
| Answer write | a constant number of primary-key statements in one transaction |

Round trips are driven to constants with recursive queries and pipelining. Rows
touched remain proportional to the tree and the collection — that is honest, and
the depth cap plus the indexes are what keep it bounded. The answer write is
`O(1)` and independent of collection size, which is the one that matters most: it
is on the path a learner waits for.

## 8. Capabilities that may not be cut

Per R4:

- One readability implementation, set-based, serving all three uses.
- A reference authorizes its target **independently** of its own container.
- A revoked target is a state, not an error, and not an empty deck.
- Breadcrumb stops at the first unreadable hop.
- Private and missing are indistinguishable.
- Generation bump and mutation in one transaction; eviction after commit.
- Redis unavailability never changes a committed outcome.
- Cycles rejected on write; read-side traversal terminates on a repeat.
- Depth cap enforced.
- Exact top-K in the database, not in the application.
- Progress identity is global per `(learner, sense)`.

## 9. Invariants for the checklist

```text
a private node and a missing node are indistinguishable
a public folder does not expose a reference's private target
a reference whose target was revoked renders as revoked, not as empty
breadcrumb stops at the first unreadable hop
a cycle is rejected on write
read traversal terminates on a repeated node
depth beyond the cap is rejected
one readability query serves single-node, batch, and breadcrumb
a structural write bumps the node, its ancestors, and referencing ancestors
a stale generation cannot serve a cached subtree
Redis down → the mutation still commits and reads still resolve
moving a deck preserves every learner-sense record
a sense in two decks is scheduled once
top-K returns at most 2K rows and the application sorts nothing
the same metric over one folder and over the account uses one predicate
```
