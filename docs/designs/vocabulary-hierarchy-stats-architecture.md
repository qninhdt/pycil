# Vocabulary Hierarchy and Statistics — Current Python Contract

**Status:** Approved architecture; integrity and API hardening in progress

**Updated:** 2026-07-16

**Scope:** hierarchy, live references, visibility, canonical sense sets, cache,
statistics, items, and history.

## 1. Current system grounding

Pycil is a backend-only Python system:

- FastAPI + SQLModel + Alembic in `apps/api`
- PostgreSQL for Pycil-owned relational and learning state
- Redis for L1 subtree caches and ephemeral sessions
- arq worker for asynchronous generation and LLM grading
- Centrifugo for owner-scoped realtime delivery
- lexi-ai behind `LexiClient`, with its own dictionary/question database

The atomic learnable unit is lexi-ai's opaque `sense_id`. Pycil stores only
`deck_senses(node_id, sense_id, position)` membership and never joins dictionary
content across the two-database boundary.

Legacy Go, ELO, `definition_id`, in-process dictionary-map, L2 cache, nightly
snapshot, and partition-first descriptions are superseded by this contract.

## 2. Hierarchy model and invariants

`nodes` is an adjacency-list tree with three types:

| Type | Children | Owns senses | Target |
|---|---|---|---|
| `FOLDER` | FOLDER, DECK, REFERENCE | no | none |
| `DECK` | none | yes | none |
| `REFERENCE` | none | no | one live DECK |

Required invariants:

- only FOLDER accepts children;
- only DECK accepts `deck_senses` rows;
- a node cannot be its own parent or move under a descendant;
- ownership edges cannot cross users;
- soft-deleted nodes do not contribute to reads;
- writes are owner-only;
- structural writes lock affected roots in stable order and recheck invariants.

Service validation owns cross-row rules such as cycle detection and live target
authorization. Database constraints and indexes enforce safe row-local rules.
Migration preflight reports cycles, cross-owner edges, invalid containers,
invalid targets, and non-DECK membership before constraints are validated. It
must not silently relocate membership or delete user structure.

## 3. Visibility and publication

Private nodes are visible only to their owner. Public DECKs are directly
readable. Publishing a FOLDER is an explicit confirmed operation that grants
inherited read visibility through its same-owner descendant tree without
rewriting descendant visibility flags. Writes remain owner-only.

Moving a private descendant outside public ancestry immediately removes that
inherited visibility. Moving it beneath public ancestry grants the inherited
read path. Existing cross-owner ownership edges are invalid and excluded.

Unauthorized private identifiers use not-found semantics so UUID enumeration
does not reveal existence.

## 4. Live references

A REFERENCE is a leaf pointing at a DECK that is either owned by the actor or
independently PUBLIC. It is a live view, not a copy:

- target membership changes appear after canonical invalidation;
- a target becoming private or soft-deleted becomes unavailable immediately;
- the reference row remains but contributes no target content;
- publication of the containing folder never overrides target authorization;
- references do not snapshot content and are not automatically deleted.

Reference-to-folder is out of scope. Supporting it later would require a
separate bounded expansion design with visited-set protection.

## 5. Canonical subtree sense set

Every accessible FOLDER, DECK, or REFERENCE resolves through one owner/public-
scoped Stage-1 relation that returns distinct `sense_id` values. The recursive
branch follows same-owner child edges; DECK nodes contribute their membership;
REFERENCE leaves contribute only currently accessible, non-deleted target DECK
membership.

This relation is authoritative for:

- folder/deck/reference study queues;
- item listing;
- learned/mastered/average statistics;
- weakest-sense selection;
- CEFR distribution;
- folder history.

Consumers must not independently reimplement subtree, deletion, publication,
reference, or deduplication semantics.

## 6. Cache integrity

L1 caches store the user-agnostic distinct sense set. PostgreSQL owns a durable
per-node structural generation. Cache keys include that generation; a cache read
must compare against the database generation before accepting a value.

Every structural mutation bumps affected generations inside the same database
transaction:

- create, move, soft-delete, and visibility/publication changes;
- add/remove deck membership;
- reference creation/removal or target visibility changes;
- direct ownership ancestors;
- reverse-reference ancestors of affected targets.

Redis deletion is best-effort after commit. An older cache fill cannot become
visible after a newer generation commits. Redis failure never changes the
reported result of a committed or rolled-back PostgreSQL mutation.

L2 user-stat caches are deliberately absent until measured load justifies them.

## 7. Statistics semantics

User learning state is global per `(user_id, sense_id)`, so one sense appearing
through multiple decks/references counts once.

| Metric | Canonical meaning |
|---|---|
| total | distinct live senses in the authorized subtree |
| learned | senses with user learning state |
| mastered | learned senses with mastery at least server threshold |
| average mastery | average over learned senses only |
| weakest | active, non-buried learned senses ordered by mastery ascending |

The mastered threshold is server-owned, defaults to `80/100`, and is not a
request parameter. Buried senses remain in documented learned totals but are
excluded from study queues and weakest results.

CEFR belongs to lexi-ai content. Pycil resolves it in batches through
`LexiClient`; missing lexi rows are skipped or flagged according to the endpoint
contract without corrupting numeric learning totals.

## 8. API contracts

Owner/public authorization is applied to each root and every live reference
target.

- `GET /folders/{id}/stats` returns total, learned, mastered, and learned-only
  average mastery.
- `GET /folders/{id}/weakest` returns bounded active, non-buried items.
- `GET /folders/{id}/cefr` returns CEFR buckets from batched lexi resolution.
- `GET /folders/{id}/items` returns paginated distinct senses and tolerates
  missing lexi rows explicitly.
- `GET /folders/{id}/history?from&to&bucket=day` enforces a maximum range and
  bucket count.
- `GET /me/stats` returns global learned, mastered, and average mastery using the
  same server-owned threshold.

Wire names of existing statistics endpoints remain backward compatible unless
a migration explicitly records a breaking contract.

## 9. History

`review_log` is append-only and written atomically with each first-attempt FSRS
mutation. It records true pre-update and post-update stability/mastery.

Folder history:

1. resolve the authorized distinct sense relation;
2. fetch each sense's latest observation before the requested window;
3. fetch bounded events inside the window using
   `(user_id, sense_id, reviewed_at)` access;
4. carry values forward into stable application-layer buckets.

This preserves the first bucket when no review occurs on the first day. Nightly
snapshots, BRIN/partitioning, TimescaleDB, and external analytics stores are
deferred until measured review-log volume/query latency requires them.

## 10. Scale-safe query strategy

Uncached reads join directly to the canonical SQL relation and avoid Python
round trips for deck/sense IDs. Cached small sets may use one bounded array or
VALUES/unnest relation. Large sets use the canonical CTE or a transaction-scoped
temporary relation; no path emits 100,000 expanding bind parameters.

Benchmarks must cover empty, 2,000-sense, and 100,000-sense subtrees. The target
for 2,000 senses is under 50 ms database-side in a representative environment.
Future results must include dataset shape and query plans, and regression gates
must compare against the recorded baseline.

## 11. Accepted and rejected alternatives

- Keep adjacency list; reject closure tables until measured recursive traversal
  cost warrants materialization.
- Keep compute-on-read; reject per-folder rollups and write amplification.
- Keep L1 only; reject L2 until user-overlay reads are measured hot.
- Reject bitmaps: sparse sense IDs and numeric averages still require relational
  state while a second truth source adds consistency risk.
- Reject in-memory dictionary copies: lexi-ai owns content behind a port and a
  separate database.
- Reject snapshots, partitioning, Kafka, ClickHouse, and TimescaleDB before an
  observed operational trigger.
- First escalation for a hot subtree relation is a measured flattened
  `node_senses` materialization, not a general DAG.

## 12. Security and validation obligations

- Private/deleted reference targets never contribute counts, items, sessions,
  CEFR data, or history.
- Publication requires explicit confirmation and never grants write access.
- Concurrent inverse moves cannot form a cycle.
- Cache miss racing a structural mutation cannot resurrect stale senses.
- Migration preflight reports invalid legacy data and supports additive
  expansion; destructive downgrade after new writes is unsupported.
- Empty, duplicate, buried, missing-lexi, 2k, and 100k cases require explicit
  tests before rollout.

## 13. Deferred work

Reference-to-folder, flattened subtree materialization, L2 caching, snapshots,
partitioning, and external analytics require separate measured triggers and
plans.
