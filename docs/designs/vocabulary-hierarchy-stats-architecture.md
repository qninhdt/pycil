# System Design: Hierarchical Vocabulary Organization & Real-Time Mastery Statistics

**Status:** Proposed (senior consolidated design) — v1
**Author role:** Senior engineer / architect review
**Date:** 2026-07-02
**Supersedes / consolidates:** `docs/designs/system_1.md` … `system_5.md` (team member proposals; treated as *reference only*)
**Scope of this doc:** the folder/deck hierarchy, the reference ("add someone else's deck to my folder") feature, and per-user statistics (learned count, mastered count, average ELO) over arbitrarily nested folders — plus how history/graphs are stored and served.
**Explicitly OUT of scope (deferred to a separate brainstorm):** the exact mastery-scoring math, the spaced-repetition scheduling algorithm, and the "which term set does *average ELO* range over" decision. This document is deliberately **scoring-agnostic** — see §12 (Open Questions).

---

## 1. Executive Summary (TL;DR)

Build the entire system on **PostgreSQL + Redis only**. No Kafka, no ClickHouse, no TimescaleDB, no bitmap/varbit/RoaringBitmap indexing, and no rewrite of the scoring engine — **until** a concrete, measured trigger is hit (§11).

The five team proposals independently reached for heavy infrastructure (ClickHouse, Kafka, TimescaleDB, Redis bitmaps, Closure Tables, an FSRS rewrite). They are solving an *imagined* problem — millions of users, a directed-acyclic graph of shortcuts, and an ELO value that decays every millisecond. **None of those three conditions holds** for this system at launch scale. This design proves, with arithmetic (§10), that a single modest Postgres instance comfortably serves **thousands of users over a 100k-definition catalog**.

Core decisions:

1. **Hierarchy = tree** (adjacency list on `parent_node_id`). Not a general DAG.
2. **Sharing = "reference leaf"**, not shortcuts-as-DAG. A `REFERENCE` node is a leaf pointing at one deck (or, later, a depth-bounded folder). This delivers ~90% of the "add someone's deck to my folder" value at ~10% of the complexity of a Closure Table. See §8.
3. **Statistics are computed on read**, never stored as per-folder rollups. This eliminates *write amplification* entirely.
4. **Two-layer cache** splits the expensive **user-agnostic** part (the folder's definition set) from the cheap **user-specific** overlay. See §7.
5. **History is an append-only `review_log`** (written in the same transaction as the review) plus a nightly **snapshot** table. Postgres range-partitioning handles this to ~100M+ rows.
6. **Definition content** (text, CEFR, audio URL, translation) is served from an **in-memory map in the Go API**, not joined from SQL on the hot path. (The one genuinely good idea borrowed from `system_5.md`.)

The design also happens to align with the **current** database schema (statistics keyed on `definition_id`, adjacency-list nodes, existing 11 mastery levels), so migration cost is low — but it is presented here as the greenfield-optimal choice on its own merits, independent of any prior project decision.

---

## 2. Problem Statement

### 2.1 What "more levels than Quizlet" actually means

The product goal — *"like Quizlet, but with more levels"* — decomposes into **two independent axes**. Conflating them is the root cause of most of the over-engineering in the reference docs.

| Axis | Quizlet | Pycil (this design) |
|---|---|---|
| **A. Organizational nesting depth** | Folder → Set (≈1–2 levels, effectively flat) | Folder → Folder → … → Deck (**arbitrary depth**) |
| **B. Mastery granularity per item** | Binary-ish ("Known" / "Still learning") | **11 mastery levels** (0 = Unseen … 10 = Expert), ELO-driven |

Axis A is a **data-structure / query problem** (how to aggregate statistics over a nested subtree). Axis B is a **learning-algorithm problem** (how a single item's score evolves) and is **deferred** (§12). This document solves Axis A and the *plumbing* around Axis B, but does not fix the scoring formula.

### 2.2 The hard requirement

For **any node** (deck or deeply nested folder), display **immediately** (target < 50 ms end-to-end), *for the current user*:

- number of items **learned**,
- number of items **mastered**,
- **average ELO / mastery score**,

…and additionally: item lists for a study session, CEFR distribution, "N weakest items", global per-user totals, and history graphs over time.

The difficulty the team feared: doing this over a nested hierarchy, for **public folders opened by many users at once**, without melting the database.

---

## 3. Grounding: What Actually Exists (the real substrate)

The five design docs are theoretical. This section records the **real data model** the design must fit, because several proposals were built on premises that do not match it.

**Stack (real):** Go (chi router) + `ent`/raw SQL over **Postgres 16**; **Redis 7**; Python worker for LLM jobs. Schema is generated from TypeSpec contracts (`contracts/**/*.tsp`) into ent / zod / SQLModel.

**Key schema facts that constrain the design:**

- **Hierarchy is an adjacency list.** `nodes.parent_node_id` (nullable). Children are fetched one level at a time (`ListChildren` in `apps/api/internal/store/node_store.go`). There is **no** closure table and **no** recursive CTE in the current code.
- **The learnable unit is the *definition*, not the *term*.** A `Term` (e.g. "bank") has multiple `Definition`s (senses). Decks contain definitions via `deck_definitions (deck_id, definition_id)`. `nodes.definition_count` counts definitions.
- **User statistics are keyed on `(user_id, definition_id)`** in `user_term_stats` — a **global-per-definition** state, *not* per-definition-per-deck. This single fact dissolves the "double-counting across the DAG" problem (§5, Fear #2) and invalidates the dense-`word_index` premise behind every bitmap proposal (§9).
- **Scores are stored integers, updated only on review.** `user_term_stats.mastery_score` (default 1000) and `mastery_level` (0–10) change only when the user answers a card (`apps/api/internal/service/learning/answer_grading.go` → `LevelForELO`). **There is no background decay job and no per-millisecond ELO.**
- **The 11 mastery levels already exist and work.** `apps/api/internal/learning/mastery_levels.go`: `LevelForELO(elo)` → bucket 0–10 with labels `Unseen … Expert`.
- **The genuine gap:** there is **no subtree aggregation** anywhere. `node_service.go` is CRUD only. Folder-level "mastered count / avg ELO" is *not built yet*. **This is the actual thing to design.**

> Note on prior "decisions": the README/rehab notes are treated as outdated per stakeholder instruction. The `SHORTCUT` enum value and `nodes.target_node_id` column still physically exist but are unused by Go code. This design **repurposes** that column for `REFERENCE` (§8) rather than inventing new schema.

---

## 4. Architecture Overview

```
                         ┌──────────────────────────────┐
                         │        Go API (chi)          │
   GET /folders/:id/stats│                              │
  ────────────────────►  │  ┌────────────────────────┐  │
                         │  │ In-memory Definition Map │  │  load @ boot (~100k defs, 15–30 MB)
                         │  │  map[int64]DefContent    │  │  → serves text/CEFR/audio/translation
                         │  └────────────────────────┘  │
                         │            │                  │
                         │   L2 cache │  L1 cache        │
                         └──────┬─────┴───────┬──────────┘
                                │             │
                      ┌─────────▼───┐   ┌─────▼──────────────┐
                      │   Redis 7   │   │    PostgreSQL 16    │
                      │ L1: folder  │   │ nodes (adj. list)   │
                      │   def-sets  │   │ deck_definitions    │
                      │ L2: (user,  │   │ user_term_stats     │
                      │   folder)   │   │ review_log (partn.) │
                      │   stats     │   │ user_daily_snapshot │
                      └─────────────┘   └─────────────────────┘
```

There is **one** synchronous path (HTTP → Go → Redis/Postgres) and **one** asynchronous path (nightly cron for snapshots). No message broker is involved in the statistics feature. (The separate real-time/notification concern in `notes.md` — Centrifugo — is orthogonal and not part of this design.)

---

## 5. Debunking the Four Fears (why heavy infra is unnecessary)

The reference docs pull in ClickHouse/Kafka/Timescale/bitmaps to defuse four fears. Each fear is either false under the real data model or cheaply handled.

### Fear #1 — "ELO decays continuously, so we must recompute every item on every read → millions of computations."
**False.** `mastery_score` is a stored integer that changes **only on review**. There is no decay job. Therefore `avg(mastery_score)` and `mastered_count` for a folder are **exactly correct until the user's next review** — trivially cacheable. Even if a later brainstorm adds retrievability-style decay, decay is a **closed-form arithmetic expression over rows we already scan**, not a separate write or a separate table.

### Fear #2 — "Aggregating a folder over a DAG needs recursive joins *and* de-duplication of items counted twice."
**False on both counts.** (a) With reference-leaves instead of shortcuts, the ownership hierarchy is a **pure tree** (real-world depth < 20); a recursive CTE on an indexed `parent_node_id` is ~1 ms. (b) Because user state is **global per definition**, aggregating a folder is a **set-union of definition ids** — a definition appearing in two decks is still one element of the set. There is no double-counting to defend against.

### Fear #3 — "Write amplification: one review changes an ELO → must update thousands of folder rollups."
**Only true if you store per-folder rollups. So don't.** Compute on read. Zero rollups ⇒ zero amplification. The cost moves to read time (~10–20 ms per uncached folder open), which we cache. The *only* upward walk we ever do is **cache invalidation on rare structural edits** (add/move/remove a node), which is O(depth) and touches cache keys, not DB rows.

### Fear #4 — "Time-series ELO graphs need TimescaleDB/ClickHouse gap-filling."
**Overkill at this scale.** An append-only `review_log` (written in the review transaction) plus a nightly snapshot table serves every graph the product needs. Gap-filling ("carry last known value forward") is done in the application layer while shaping the series. Millions of log rows are nothing for a range-partitioned Postgres table with a BRIN index on time. Timescale/ClickHouse become worth their operational cost only past ~100M rows — far beyond thousands of users.

---

## 6. Data Model

Notation: PK = primary key, FK = foreign key. Types match the existing TypeSpec/Postgres schema.

### 6.1 Hierarchy

```
nodes
  id             uuid       PK
  author_id      uuid       (index)         -- owner
  type           text       -- 'FOLDER' | 'DECK' | 'REFERENCE'
  parent_node_id uuid null  (index)         -- adjacency list; NULL = root
  target_node_id uuid null                  -- USED ONLY when type='REFERENCE'
  name           text
  description    text null
  visibility     text       -- 'PRIVATE' | 'PUBLIC'
  definition_count int      -- own decks only; denormalized convenience count
  likes_count    int
  forks_count    int
  created_at / updated_at / deleted_at (soft delete)
```

- **FOLDER**: may contain FOLDER / DECK / REFERENCE children. `target_node_id` NULL.
- **DECK**: leaf that owns definitions via `deck_definitions`. `target_node_id` NULL.
- **REFERENCE**: **leaf** (no children). `target_node_id` → a DECK owned by anyone (or, in a later iteration, a folder). It contributes the target's definition set when a subtree is resolved. See §8.

Supporting tables (existing, unchanged): `folder_attributes(node_id, subfolder_count)`, `deck_attributes(node_id, settings jsonb)`, `user_nodes(user_id, node_id, is_starred, is_pinned)`.

### 6.2 Content (existing, unchanged)

```
terms        (id PK, type, value, source, …)
definitions  (id PK, term_id (index), cefr_level, part_of_speech,
              translation jsonb, tts_url jsonb, is_primary, sense_index, …)
deck_definitions (deck_id, definition_id, position)   PK(deck_id, definition_id)
deck_terms       (deck_id, term_id, position)         PK(deck_id, term_id)
```

The **atomic learnable unit is `definition_id`**. All statistics range over sets of `definition_id`.

### 6.3 Per-user learning state (existing; canonical)

```
user_term_stats
  user_id         uuid       PK
  definition_id   int64      PK          -- note: keyed on definition, despite the name
  mastery_score   int  = 1000            -- the "ELO"; stored, updated only on review
  mastery_level   int16 = 0              -- 0..10 bucket (0 = Unseen)
  last_review_date / next_review_date  timestamptz null
  review_count    int
  interval_seconds float64               -- SRS scheduling state (algorithm deferred)
  status          text  -- 'active' | 'suspended' | 'buried'
  buried_until    date null
  lapse_count     int
```

> **Cleanup flag (open item, §12):** a second table `user_definition_stat(elo=800, totalSeen, totalCorrect, …)` also exists and appears to overlap. The learning code path uses `user_term_stats`. Confirm and consolidate before building; this design treats `user_term_stats` as canonical.

### 6.4 History: append-only review log (NEW)

```
review_log                              PARTITION BY RANGE (reviewed_at)  -- monthly
  id            bigint  identity
  user_id       uuid
  definition_id int64
  node_id       uuid null      -- deck the review happened in (context; optional)
  elo_before    int
  elo_after     int
  level_before  int16
  level_after   int16
  grade         int16          -- raw answer outcome (again/hard/good/easy or 0/1)
  reviewed_at   timestamptz
Indexes:
  BRIN (reviewed_at)                     -- cheap, ideal for append-only time data
  BTREE (user_id, reviewed_at)           -- per-user history scans
Retention: monthly partitions; compress/detach partitions older than N months.
```

Written **in the same transaction** as the `user_term_stats` upsert. One extra INSERT per review — negligible.

### 6.5 History: nightly dashboard snapshot (NEW)

```
user_daily_snapshot
  user_id        uuid
  snapshot_date  date
  total_learned  int
  total_mastered int
  avg_elo        float
  PRIMARY KEY (user_id, snapshot_date)
```

Populated by a nightly cron from the **current** `user_term_stats` (one row per active user per day). Powers the global dashboard trend cheaply; folder-scoped history is derived from `review_log` on demand (§7.6).

---

## 7. Read Paths (the hot queries)

All folder-scoped queries share **Stage 1** (resolve the folder's definition set — *user-agnostic*, heavily cached) and then a **Stage 2** overlay (*user-specific*).

### 7.1 Stage 1 — resolve a folder's definition set (user-agnostic)

```sql
WITH RECURSIVE subtree AS (
    SELECT id, type, target_node_id
    FROM nodes
    WHERE id = $folder_id AND deleted_at IS NULL
  UNION ALL
    SELECT n.id, n.type, n.target_node_id
    FROM nodes n
    JOIN subtree s ON n.parent_node_id = s.id     -- walk owned tree downward
    WHERE n.deleted_at IS NULL
),
resolved_decks AS (
    SELECT id AS deck_id            FROM subtree WHERE type = 'DECK'
    UNION
    SELECT target_node_id AS deck_id FROM subtree
      WHERE type = 'REFERENCE' AND target_node_id IS NOT NULL   -- reference leaves
)
SELECT DISTINCT dd.definition_id
FROM resolved_decks rd
JOIN deck_definitions dd ON dd.deck_id = rd.deck_id;
```

Result is a **set of `definition_id`**. Cache it (see §7.7). Recursion depth = tree depth (small); the recursion never follows references into further recursion because a reference resolves to a **deck leaf**.

### 7.2 Query 1 — folder statistics for the current user

Prefer a **JOIN against the cached/derived set** over `= ANY(array)` when the set can be large (§10 explains why array marshaling is the real cost at 100k):

```sql
-- :folder_defs is the Stage-1 result (cached set, or the CTE inlined)
SELECT
    (SELECT count(*) FROM folder_defs)                              AS total_defs,
    count(uts.definition_id)                                        AS learned,
    count(uts.definition_id) FILTER
        (WHERE uts.mastery_level >= :mastered_level_threshold)      AS mastered,
    COALESCE(avg(uts.mastery_score), 0)::float                      AS avg_elo
FROM folder_defs fd
LEFT JOIN user_term_stats uts
       ON uts.definition_id = fd.definition_id
      AND uts.user_id = :user_id;
```

- `total_defs` = folder size (user-agnostic).
- `learned` = definitions the user has a stat row for.
- `mastered` = level ≥ threshold. `:mastered_level_threshold` is a **parameter** (default 8 = "Mastered-1" in the current level table), *not* hard-coded — the mastery brainstorm may move it.
- `avg_elo` here averages over **learned** items. Whether it should instead average over **all** folder items (with a baseline for unseen) is **deferred** (§12) — the query supports either by changing the FROM side.

### 7.3 Query 2 — item list for a study session / display

1. DB returns the ordered `definition_id[]` for the deck/folder (Stage 1, or `deck_definitions` for a single deck).
2. Go enriches each id from the **in-memory `map[int64]DefContent`** (text, CEFR, part of speech, translation, TTS URL) — **no `JOIN definitions` on the hot path**.
3. If per-user overrides exist (`definition_override`, `term_note`), overlay them in Go at read time.

Rationale: ~100k definitions of content is ~15–30 MB resident — trivial to hold in each API instance and refresh on change. This removes the single largest, most repetitive JOIN from every list request.

### 7.4 Query 3 — N weakest items in a folder (for "review weak words")

```sql
SELECT uts.definition_id, uts.mastery_score
FROM folder_defs fd
JOIN user_term_stats uts
       ON uts.definition_id = fd.definition_id
      AND uts.user_id = :user_id
WHERE uts.status = 'active'
ORDER BY uts.mastery_score ASC
LIMIT :n;
```

Top-N over the user's *learned* subset (small) — a few milliseconds. Content is enriched in Go (§7.3). No index on the volatile score is needed; the working set is tiny.

### 7.5 Query 4 — CEFR distribution of a folder (user-agnostic)

CEFR is a property of the definition, identical for everyone. Two options:

- **(Recommended) Compute in Go** from the in-memory map over the Stage-1 set: iterate the definition ids, bucket by `DefContent.Cefr`. Sub-millisecond, no DB round trip.
- **SQL fallback**: `SELECT cefr_level, count(*) FROM folder_defs fd JOIN definitions d ON d.id = fd.definition_id GROUP BY cefr_level`.

Cache the result alongside the Stage-1 set (same invalidation lifecycle).

### 7.6 Query 5 — history graph (ELO / mastered count over time) for a node

1. Take the Stage-1 definition set for the node.
2. Read `review_log` for `(user_id, definition_id ∈ set, reviewed_at ∈ window)`, ordered by time.
3. In the application layer, **carry-last-value-forward** across day buckets to fill gaps, then average / count per bucket.

Global dashboard trend reads `user_daily_snapshot` directly (already bucketed). Only folder-scoped history touches `review_log`, and only for the requested window (partition pruning + BRIN keep it fast).

### 7.7 Query 6 — global per-user totals (dashboard)

```sql
SELECT
    count(*)                                                   AS learned,
    count(*) FILTER (WHERE mastery_level >= :threshold)        AS mastered,
    COALESCE(avg(mastery_score), 0)::float                     AS avg_elo
FROM user_term_stats
WHERE user_id = :user_id;
```

Bounded by the user's learned set (≤ number of definitions they've touched). Cache with a short TTL, bust on review.

### 7.8 Caching strategy (two layers)

| Layer | Key | Content | Invalidation |
|---|---|---|---|
| **L1 (user-agnostic)** | `node:{id}:defset:v{struct_version}` | Stage-1 definition set (+ CEFR counts, total) | On **structural edits only** (add/remove/move node, add/remove reference, deck gains/loses a definition). Walk ancestors via `parent_node_id` and bust their keys — O(depth), cache-only. |
| **L2 (user-specific)** | `stats:{user}:{node}` | Final `{learned, mastered, avg_elo}` | Short TTL (30–60 s) **and** busted when *that user* reviews. |

The asymmetry is the whole point: the expensive part (subtree resolution) is shared across all users viewing a public folder and rarely changes; the per-user part is a cheap overlay. This is the correct answer to *"a public folder opened by thousands of users, each wanting their own progress"* — the heavy computation is done once and reused; only the small overlay is per-user.

**Why this is not write amplification:** on a review we bust `stats:{user}:*` (cheap, lazy recompute) — we do **not** recompute or rewrite any folder rows. On a *structural* edit (rare) we bust `node:{ancestors}:defset` cache keys — again, no DB rollup rows to update.

---

## 8. The Reference-Leaf Design (sharing without a DAG)

**Product need:** "add someone else's public deck (or folder) into my own folder," like Google Drive's *Add shortcut to Drive*.

**Rejected approach:** modeling this as a general DAG with a **Closure Table** (as four of the five docs propose). A Closure Table requires: a Cartesian-product insert on every link, cycle detection before every insert, and O(descendants × ancestors) row churn when a subtree moves. That complexity buys a generality this product does not need.

**Chosen approach: `REFERENCE` as a leaf.**

- A `REFERENCE` node lives in the owner's tree like any child, but has **no children of its own** and carries `target_node_id` → a **DECK**.
- During Stage-1 resolution (§7.1), a `REFERENCE` contributes its **target deck's definition set**. Because user state is global-per-definition, this composes by **set union** — automatically de-duplicated, no double counting.
- **Cycle safety is free**: a reference points to a deck (a leaf), so subtree resolution cannot recurse through it. There is no cycle to detect.

**Correctness detail — sharing vs. copying:** a reference is a *live view* of the target deck. If the target author adds definitions, the reference reflects them on next resolution (after L1 cache expiry/bust). This is distinct from **DeckClone** (existing table), which is a *copy* taken at a point in time. Both are legitimate product features; keep them separate and clearly labeled in the UI ("Add shortcut" = reference/live vs. "Clone" = copy/independent).

**Deferred generalization (not in this round):** allowing a reference to target a *folder* (not just a deck). That reintroduces multi-level resolution and therefore needs a **visited-set + max-depth guard** during Stage-1 to stay acyclic and bounded. The design leaves a clean seam for this: Stage-1's `resolved_decks` CTE would expand folder references with a depth-limited recursive branch. Ship deck-references first.

---

## 9. Why NOT Bitmaps / varbit / RoaringBitmap

Three of the five docs propose representing each user's progress as a dense bit array indexed by a contiguous `word_index ∈ [0, N)`, then answering "count learned in folder" via `BITCOUNT(user AND folder)`.

Reasons this is rejected for this system:

1. **The premise doesn't hold.** State is keyed on `definition_id` (a sparse `int64`), not a dense `word_index`. A term has many definitions; there is no natural 0..N dense index without inventing and maintaining a parallel id space.
2. **It only accelerates *counting*.** `learned` and `mastered` are boolean counts — but **`avg_elo` is not boolean**. Averaging still requires reading a numeric score per item (the docs that go bitmap end up bolting on a separate "dense ELO array" — reintroducing exactly the per-item scan the bitmap was meant to avoid).
3. **Postgres already counts 100k narrow rows in single-digit milliseconds** (§10). There is no counting problem to solve.
4. **Bitmaps add a second source of truth** that must be kept consistent with the relational state via events — a classic eventual-consistency bug surface, for a speedup we don't need.

If, after profiling, folder counting ever becomes hot enough to matter (it won't at thousands of users), the *first* escalation is a **flattened `node_definitions` table** (§11), not bitmaps.

---

## 10. Performance Analysis (the arithmetic that replaces the fear)

Assumptions (deliberately conservative): **5,000 registered users**, **500 concurrent at peak**, **100,000 definitions** in the catalog, a typical folder holding **500–2,000 definitions** (worst case: a folder that transitively contains the entire catalog = 100k).

**Postgres aggregate throughput:** a modern core scans on the order of **50–150M narrow rows/second** for `count`/`avg` over an indexed set. `user_term_stats` rows are narrow (a handful of ints + a uuid + timestamps).

| Operation | Cost | Reasoning |
|---|---|---|
| Stage-1 subtree resolve (recursive CTE, typical) | **1–5 ms** | Tree depth < 20, indexed `parent_node_id`; hits `deck_definitions` by PK. Cached in L1 afterward. |
| Query 1 folder stats, typical folder (≤2k defs), L1 hit | **~2–5 ms** | LEFT JOIN of ≤2k ids against `user_term_stats` PK lookups. |
| Query 1 worst case (folder = entire 100k catalog) | **~15–30 ms** | 100k PK probes + aggregate. Still under the 50 ms budget — *before* caching. |
| Peak folder-open request rate | **~33 req/s** | 500 users × 1 open / 15 s. |
| Read CPU (uncached) | **< 1 core** | 33 × ~20 ms ≈ 0.66 core-seconds/s. With L1+L2 cache, most requests never hit Postgres. |
| Review writes | **~150–300 ops/s** | 500 users × ~20 cards/min ≈ 167/s; each = 1 upsert + 1 log insert. Postgres does thousands/s. |
| `review_log` growth | **~1–5M rows/month** | Trivial with monthly partitions + BRIN. 100M rows = tens of GB, still fine. |
| In-memory content map | **~15–30 MB/instance** | 100k definitions of text/metadata. |

**The critical implementation nuance at 100k:** do **not** pass a 100k-element array to `= ANY($1)` — marshaling ~800 KB of int64 and planning against it is the real bottleneck, not the aggregation. Keep the definition set as a **CTE/subquery or cached temp set and JOIN** against it. For cached L1 sets, store as a compact serialized array and, for large folders, load into a `TEMP TABLE` or use `unnest($1) JOIN` with a single bind.

**Conclusion:** one modest Postgres 16 instance + Redis serves the stated scale with comfortable headroom. The "billions of rows" that motivated ClickHouse/Kafka in the reference docs correspond to *1M+ users × years of logs* — a different product phase, addressed by the escalation path below, not by launch-day infrastructure.

---

## 11. Scaling Triggers (when — and only when — to add complexity)

Each item is gated on a **measured** condition, not a hunch:

| Trigger (measured) | Escalation | Not before |
|---|---|---|
| Stage-1 recursive CTE shows up hot in `pg_stat_statements` | Add a **flattened `node_definitions(node_id, definition_id)`** materialization (union set, refreshed on structural edits) — still not a full closure table | It's hot in profiling |
| A few public folders opened by thousands simultaneously | Longer-TTL L1 cache of the user-agnostic set + CEFR counts; per-user overlay stays tiny | L2+L1 miss rate is actually high |
| `review_log` approaches ~100M rows and history queries slow | Adopt **TimescaleDB** (same Postgres, least disruption) — hypertables + continuous aggregates | 100M rows |
| Multi-dimensional real-time analytics become a product pillar | Consider **ClickHouse** as an OLAP sink fed from `review_log` | There's a real analytics product |
| Real-time notifications / async LLM grading handoff | **Centrifugo** (see `notes.md`) — orthogonal to statistics | That feature is scheduled |
| Reference-to-folder (not just deck) is required | Extend Stage-1 with depth-bounded, visited-set folder expansion | Product asks for it |

---

## 12. Open Questions (explicitly deferred — do NOT decide silently)

1. **[DEFERRED — separate brainstorm] Mastery scoring & spaced-repetition algorithm.** Whether to keep the current ELO + SM-2-style scheduling, adopt FSRS-style retrievability, or a hybrid. This design is **scoring-agnostic**: it stores whatever scalar the algorithm produces (`mastery_score`) and buckets it (`mastery_level`), and never assumes a specific update rule. The chosen algorithm plugs in at the review write path (§6.4) without touching the aggregation/caching design.
2. **[DEFERRED] Average-ELO basis.** Does folder `avg_elo` range over **only learned** items (cheapest, current query) or over **all** items in the folder with a baseline for unseen (reflects completion %)? Both are one-line changes to Query 1's FROM side. To be decided together with #1.
3. **[NEEDS CONFIRMATION] Duplicate stat tables.** `user_term_stats` vs `user_definition_stat` overlap (§6.3). Confirm which is canonical and consolidate before building aggregation on top.
4. **[CONFIRM] `mastered` threshold.** Parameterized default = level ≥ 8. Final value belongs to brainstorm #1.
5. **[LATER] Reference-to-folder** targets (§8) — deferred generalization.

---

## 13. What This Design Rejects From the Reference Docs (traceability)

| Proposal (source doc) | Verdict | Rationale |
|---|---|---|
| Closure Table for hierarchy (`system_1,2,3,5`) | **Reject** | Tree, small depth; recursive CTE suffices. Closure = write churn on move, complexity for a DAG we don't have. Replaced by reference-leaf (§8). |
| FSRS rewrite (`system_1,5`) | **Defer** | Core learning-algorithm change; belongs to the deferred scoring brainstorm (§12), not the folder/stats design. |
| Redis bitmaps / `varbit` / RoaringBitmap (`system_3,4,5`) | **Reject** | Wrong premise (no dense index), only speeds counting (not avg), Postgres already fast enough, adds a consistency-bug surface (§9). |
| ClickHouse / Kafka / TimescaleDB (`system_1,2,5`) | **Defer** | Unnecessary at scale (§10); gated behind explicit triggers (§11). |
| CQRS + event stream for stats (`system_2,4`) | **Reject (for stats)** | Compute-on-read + cache removes the write-side pressure CQRS was meant to relieve. |
| In-memory definition/content map in the API (`system_5`) | **Adopt** | Genuinely removes the biggest repetitive JOIN from the hot path (§7.3). |
| Compute-at-read, no per-folder rollups (`system_1,5`) | **Adopt** | Correct write-amplification defense (§5, Fear #3). |
| `time_bucket_gapfill` / LOCF idea (`system_1,2`) | **Adopt the idea, not the tool** | Gap-fill done in app over `review_log`; Timescale only if row counts justify it (§7.6, §11). |

---

## 14. Glossary

- **Definition** — a single sense of a term; the atomic learnable unit; the key of all statistics.
- **Node** — a row in `nodes`: a FOLDER, DECK, or REFERENCE.
- **Reference leaf** — a NODE of type REFERENCE pointing (`target_node_id`) at a deck; contributes that deck's definitions to the owner's subtree without copying (§8).
- **Stage-1 set** — the user-agnostic set of `definition_id` reachable under a node; the cacheable core of every folder query.
- **Mastery level** — integer bucket 0–10 derived from `mastery_score` (`LevelForELO`); the "levels" axis of the product.
- **Write amplification** — a single logical write fanning out into many physical writes; avoided here by never storing per-folder rollups (§5, §7.8).

---

*End of design. Scoring/SRS algorithm and average-ELO basis are intentionally left open for the next brainstorm; everything in this document is designed to remain valid regardless of how those are resolved.*
