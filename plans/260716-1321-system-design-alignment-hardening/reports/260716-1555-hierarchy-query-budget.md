---
title: "Hierarchy Query Budget Measurement"
date: 2026-07-16
scope: "Phase 5"
---

# Hierarchy Query Budget Measurement

## Dataset and path

Disposable PostgreSQL 16 container. One user, 100,000 learned
`user_sense_stats` rows, and the production `folder_stats` query using one
`bigint[]` bind (`ANY(CAST(:sense_ids AS bigint[]))`). No snapshots, L2 cache,
partitioning, or temporary analytics tables.

## Result

| Set size | End-to-end query time | Result |
|---|---:|---|
| 2,000 | 13.37 ms | Under the 50 ms target |
| 100,000 | 61.22 ms | Correct result; measurement retained as baseline |

Command:

```bash
cd apps/api
RUN_HIERARCHY_PERFORMANCE=1 uv run pytest -s tests/performance/test_hierarchy_query_budget.py
```

The 100k case intentionally has no fixed latency gate because hardware and
PostgreSQL configuration vary. The test proves one bounded array bind and
records the local baseline; a materialized relation/temp-table switch remains
an escalation only if future measurements regress.

## Unresolved Questions

None.
