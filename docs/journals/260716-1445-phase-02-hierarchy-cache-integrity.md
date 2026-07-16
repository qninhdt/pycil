---
title: "Phase 2 — Hierarchy and Cache Integrity"
date: "2026-07-16"
plan: "260716-1321-system-design-alignment-hardening"
phase: 2
status: complete
---

# Phase 2 — Hierarchy and Cache Integrity

## Context

Phase 2 made the canonical subtree relation safe to use by future sessions and
statistics work. It hardened hierarchy writes, live reference reads, and cache
invalidation without changing the two-database boundary.

## What happened

- Added additive migration `0002_hierarchy_integrity`: preflight failures for
  invalid legacy hierarchy data, a reference target-shape constraint, target
  index, and persisted structural generations.
- Centralized locked hierarchy mutations: FOLDER-only containment,
  same-owner edges, cycle rejection, DECK-only membership, and authorized live
  DECK reference targets.
- Added explicit public-folder publication confirmation and inherited,
  same-owner read visibility; writes remain owner-only.
- Made reference resolution live: inaccessible or deleted targets (including
  deleted ancestry) no longer contribute senses.
- Replaced delete-only cache invalidation with DB-generation Redis keys,
  reverse-reference invalidation, viewer scoping, and safe Redis-failure
  fallback.
- Added migration, visibility/revocation, and cache-race regression coverage;
  the eight Phase 2 contract cases now pass.

## Decisions

- PostgreSQL structural generations are authoritative; Redis cleanup is only
  best-effort.
- A public folder exposes its same-owner descendant subtree through effective
  read access, without mutating child visibility flags.
- References are live views, never snapshots; target authorization is checked
  during each resolution.

## Next

Phase 3 can consume the canonical, viewer-aware subtree sense set for Redis
study sessions and question delivery.
