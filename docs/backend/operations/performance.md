# Isolated query-plan and load verification

Correctness tests and defensive limits are not production capacity certification.
The opt-in matrix uses automatically owned disposable PostgreSQL/Redis, real schemas,
Lexi reads and application services, blocking paid inference. It never uses runtime
database URLs. No load command targets an application/production host.

From repository root:

```sh
PERF_TIER=small python scripts/test_api.py tests/performance/test_read_matrix.py -q
PERF_TIER=medium python scripts/test_api.py tests/performance/test_read_matrix.py -q
```

`PERF_OUTPUT` optionally selects an approved artifact directory; default
`/tmp/opencode/pycil-performance`. Reports are UUID-named JSON with PostgreSQL settings,
host information, seed dimensions, SELECT query counts, first-read timing, grouped
and individual 4-request concurrent timings, advisory lock round-trip durations,
observed throughput/errors and native-schema-aware
`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`. No credentials are serialized.

| Tier | Background users | Nodes | States / receipts each |
| --- | ---: | ---: | ---: |
| Small | 10 | 500 | 1,000 |
| Medium | 1,000 | 10,000 | 100,000 |
| Large | 100,000 | 1,000,000 | 10,000,000 |

The hot owner has 50 public and 50 private 1,000-sense decks: the 100,000 owned
membership bound. Two remote published owners add 100,000 reachable memberships;
cyclic references and ten aliases reach the exact 200,000 physical scope bound.
Decks overlap on 1,000 native lexical senses. Background memberships are sparse
(one per deck), while receipt and activity rows are populated independently.
Thirty native question banks use deterministic generation-provider output only.

Thirty workload cases cover joint 5/50-card counts, inline cards, empty/large/max-work
scope summaries, reference cycles/aliases, context, native previews/sources, scoped/
catalog FTS, owner/type browsing, activity/schedule, immutable replay, overlapping
writes, NEW/DUE/AUTO hydration/sparse readiness and sense search/sorts. Native hot
search and fresh native startup/global index refresh are separate cases. The refresh's
whole-dictionary projection is not portrayed as page-local SQL.

Native content is initially cold at the process cache boundary, not guaranteed cold
at PostgreSQL/OS buffer boundaries. Five groups / twenty request timings per workload
are smoke-load measurements, not statistically reliable long-running p99 or an HTTP
deployment SLA. Advisory round-trip durations include lock wait and driver/server
overhead, not pure PostgreSQL lock wait. Other local tests can contend on the host.
Native dictionary size is only 1,000 senses; this does not certify million-word scaling.
SQL EXPLAIN replay restores the originating public versus Lexi search path. Failed
reports may be partial; only a passing complete run is evidence for that matrix.

Large load is resource-gated and has **not** been run without explicit approval:

```sh
PERF_TIER=large PERF_LARGE_APPROVED=1 python scripts/test_api.py tests/performance/test_read_matrix.py -q
```

Before setting that approval, agree disk/memory/time, deployment hardware, workload
mix and p95/p99/throughput/error thresholds. Review rows, loops, filters, buffers,
heap fetches and spills, not just duration. Selective application reads should not
unnecessarily scan global progress or hydrate the entire dictionary. Broad FTS rank
and Lexi's global search-index refresh remain candidate/dictionary-dependent.

No production capacity or latency/QPS promise follows from this local suite. Additional
long-duration HTTP/process/lock-wait and maximum-remote-scope workloads plus approved
thresholds remain an explicit capacity gate.

## Archived passing local evidence — 2026-10-06

Each completed tier passed independently. Reports contain **30 workloads and 167 JSON
EXPLAIN plans** (SELECTs only, not re-executed mutations). Full compressed reports:

- [Small](../evidence/performance-small.json.gz), original
  `small-9a78dbcc21d84799927d3f1ff28c2a1d.json`;
  uncompressed SHA-256 `d079c0561f73bd20858d77d5e0ea4da428b1162731b39606063a518d8cdd9095`.
- [Medium](../evidence/performance-medium.json.gz), original
  `medium-179872d27eb84da8b409ba686bf2b02e.json`;
  uncompressed SHA-256 `8dc03a93e3954e86b81632a81aaeb006b051f0baacac1cebe7d650ff7364584f`.

Host: Linux x86-64, 12 logical CPUs; PostgreSQL 18.6, shared_buffers 128 MiB,
work_mem 4 MiB, max_connections 100; one in-process harness, concurrency four.
Stores are tmpfs-backed; this is not a deployment hardware specification.
Per-request p95 is descriptive of twenty samples, not an SLA.

| Workload | SELECTs | Small first / p95 ms | Medium first / p95 ms |
| --- | ---: | ---: | ---: |
| 5 cards | 4 | 61.52 / 144.57 | 59.95 / 135.44 |
| 50 cards | 4 | 92.32 / 277.83 | 75.96 / 247.63 |
| 200k-membership Library | 9 | 198.41 / 554.11 | 165.08 / 547.00 |
| Discovery browse | 2 | 38.00 / 62.17 | 357.31 / 205.81 |
| Broad catalog FTS | 2 | 37.84 / 73.06 | 127.64 / 210.57 |
| 30-word previews | 3 | 21.93 / 10.91 | 23.18 / 12.94 |
| Native global refresh | 5 | 72.95 / 271.13 | 55.62 / 153.10 |
| Overlapping writes | 5 | 9.89 / 24.54 | 9.25 / 25.36 |

Medium inspection found **no sequential scan of global `user_senses` or `review_log`
and no temporary block writes** in captured SELECTs. Native refresh intentionally
scans all 1,000 words. Sense lemma/no-match reads also use small lexical scans where
the hot scope equals the dictionary fixture; these plans do not prove every larger
dictionary planner choice optimal. JSON enrichment is bounded to selected IDs.
Catalog work grows with candidates; redundant root checks were removed without
weakening authorization. No persistent summary cache, hidden bound reduction or
unapproved large-tier run was used.

## Search query change — 2026-10-06

The medium matrix was rerun before and after candidate-first node search. Both
runs used the same disposable-store fixture and added Library-root search across
the 200,000 reachable memberships. Full 31-workload reports and EXPLAIN plans:
[before](../evidence/performance-search-before-medium.json.gz) (uncompressed
SHA-256 `d1004106374940420a2499802045ad2f785e7dfb66fa5cc7952150d6dc5df271`)
and [after](../evidence/performance-search-after-medium.json.gz) (uncompressed
SHA-256 `1439e31887dd5735e59efe39e1eba3319fb033cc05fbc4e12d381c628c0a3872`).

| Workload | Before SELECTs / p50 / p95 ms | After SELECTs / p50 / p95 ms |
| --- | ---: | ---: |
| Published-folder search | 5 / 96 / 260 | 5 / 97 / 246 |
| Library-root search | 9 / 196 / 412 | 8 / 195 / 391 |
| Discovery browse | 2 / 171 / 359 | 3 / 50 / 265 |
| Broad Discovery FTS | 2 / 171 / 185 | 3 / 56 / 60 |

The before plans scanned all 26,762 `node_paths` rows for each listed search
workload. The after plans contain no executed sequential scan of that table.
Library-root search no longer queries `deck_senses` (two queries before), while
the existing published-order index supplies Discovery browse candidates. The
candidate batch is still checked against physical ancestry; a stale `space`
value alone cannot publish a private node. Root-search request latency changed
little even though its database work fell, so the measured benefit there is
lower query cost and less catalog-dependent work, not a demonstrated latency
speedup. The 20-request p95 values remain smoke measurements, not an SLA.

## Library-root search follow-up — 2026-10-06

The profiled medium reports are [before](../evidence/performance-search-profile-before-medium.json.gz)
(uncompressed SHA-256
`7389bc5e855da0f5f04d94e120de4e6e0c513fbb7256182bd2c99b88f62209af`)
and [after](../evidence/performance-search-inline-reference-medium.json.gz)
(uncompressed SHA-256
`05e5f7e547846eba637802309ab35caa134bfcd89012e9d602d3d302f24283c9`).
The change checks reference visibility while reading each scope frontier, removing the
separate reference SELECT at each of the two frontiers reached by the fixture.
The report's `first_query_ms` includes the `set_config` statement and measures
driver plus database time; `first_ms` also includes application work.

| Medium workload | Before SELECTs / first / request p50 ms | After SELECTs / first / request p50 ms |
| --- | ---: | ---: |
| Library-root search (`bank`) | 8 / 78.5 / 172.6 | 6 / 64.5 / 159.4 |
| Discovery browse | 3 / 24.3 / 46.4 | 3 / 32.1 / 43.0 |
| Broad Discovery FTS (`catalog`) | 3 / 30.5 / 48.8 | 3 / 28.6 / 50.8 |

For the first Library-root request, measured SQL time fell from 33.9 to 25.2 ms.
The remaining time includes scope graph construction, SQLAlchemy statement
compilation, and result handling. Library-root search authorizes its root and
traverses physical descendants and reference targets before applying FTS.
Discovery uses published candidates directly and authorizes only the candidate
page. Neither Library-root run read `deck_senses`. The Library and Discovery FTS
rows use different terms and candidate populations, so their latencies are
diagnostic, not a controlled head-to-head search comparison. The p50 change is
a local smoke result; p95 varied substantially across runs.
