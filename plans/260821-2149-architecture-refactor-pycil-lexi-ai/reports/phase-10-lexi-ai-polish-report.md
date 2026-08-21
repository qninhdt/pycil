# Phase 10 Report — lexi-ai Ports Polish Batch

Agent: ox-alpha (implementer), 2026-08-21.
Repo: /home/qninh/projects/lexi-ai, branch `refactor/architecture-polish`. NOT committed (controller commits).

## Verification

- `uv run pytest -q` → 640 passed, 11 skipped (0 failed).
- `uv run lint-imports` → 5 kept, 0 broken (138 files, 436 deps).
- `uv run ruff check lexi_ai tests` → clean.
- grep: zero sqlalchemy references in `lexi_ai/application/**/*.py`; `application/question_ports.py` deleted.

## Acceptance Criteria

1. **AssetStore port typed** — `domain/ports.py` put_text/put_file now carry the full impl signatures
   (`source_kind, source_id, kind, params, source_text, text_value|data, ext, meta=None`). Impl conforms;
   pinned by `tests/test_assets.py::test_asset_repository_conforms_to_the_asset_store_port`
   (signature name/kind/default equality per port method + surface allowlist) and a behavioral round trip
   through the port-typed consumer (`test_asset_service_round_trips_through_the_typed_port`).
2. **Zero sqlalchemy in application** — `SenseEntryLoader` moved to
   `infrastructure/question_engine_factory.py` (its only constructor); miss translated at the repo edge:
   `SenseRepo.word_id_for -> int | None` via `scalar_one_or_none()` (precedent: EntryRepo.entry).
   `questions/engine.py` now types against the existing Protocol in `questions.base`.
   `application/question_ports.py` deleted. `themes.sense_view` raises `ThemeTargetInvalid` on unknown sense
   (was NoResultFound; both are ValueError-family at the facade boundary — see concerns).
3. **Single source dispatch** — `_resolve_source` consumes `_anchor` (the one dispatcher) plus new
   `_existing_entry` holding the non-force existence shortcuts. Behavior preserved exactly: str path,
   lexi_word_id shortcut, cambridge generated_by_cambridge lookup, neither-id ValueError, force semantics.
   Verified by full test_generation/test_api/test_facades suites.
4. **asset_repo split** — new `infrastructure/db/asset_file_store.py` (`AssetFileStore`: relative_path
   sanitizing, staged+fsynced writes, atomic replace, identity-checked unlinks, orphan sweep with managed/
   temp filename grammar). `asset_repo.py` keeps SQL identity upserts/read-verify/GC coordination and the
   transaction-coupled deferred-unlink listeners + file lock. content_hash read-time verification untouched
   (same `get()` logic; hash-verify tests pass unchanged). AssetStore port unchanged.
5. **Typed errors** — `EmbeddingUnavailable` relocated to `domain/errors.py`; embeddings.py imports it
   (name still importable from `lexi_ai.embeddings`, so test imports unchanged). Themes' 7 plain ValueErrors
   → `ThemeError(ValueError)` family in domain/errors.py: `UnknownTheme` (update/resolve_or_raise),
   `InvalidThemeName` (create), `ThemeTargetInvalid` (word not done / no senses / unknown sense_id ×2),
   `ThemedOverlayMissing` (append_examples). Messages byte-identical; all subclass ValueError so every
   existing handler keeps working. Branchability pinned by isinstance asserts in test_theming +
   test_services_with_fakes (+ new empty-key create test).
6. **PrepareReport re-homed** — defined in `contracts/questions.py` (dependency-free, slots style matching
   neighbors), exported via `contracts/__init__`, re-exported by `questions/base` for the plugin surface,
   root lazy map now sources it from `lexi_ai.contracts.questions`. Name and lazy behavior preserved.
7. **Docs sync** — system-architecture.md package layout rewritten to the actual tree: repositories list,
   asset_file_store, contracts/, prompts top-level (was generation/prompts), assets/ = providers only,
   questions/render+dedup, embeddings/vectors root modules, errors.py family description.
8. Both gates green (above).

## Files

Modified: docs/system-architecture.md, lexi_ai/{__init__,embeddings}.py, lexi_ai/domain/{errors,ports}.py,
lexi_ai/application/{generation,questions,themes}.py, lexi_ai/contracts/{__init__,questions}.py,
lexi_ai/questions/base.py, lexi_ai/infrastructure/question_engine_factory.py,
lexi_ai/infrastructure/db/repositories/{asset_repo,sense_repo}.py,
tests/{test_assets,test_facades,test_repositories,test_services_with_fakes,test_theming}.py.
Created: lexi_ai/infrastructure/db/asset_file_store.py (~230 lines).
Deleted: lexi_ai/application/question_ports.py.

## Concerns

1. `docs/codebase-summary.md:61` still lists the deleted `question_ports.py` — outside this phase's file
   ownership (only system-architecture.md was owned); needs a docs pass or explicit approval.
2. `themes.sense_view` unknown-sense failure changes exception type from sqlalchemy NoResultFound to
   `ThemeTargetInvalid` (a ValueError). No caller caught NoResultFound (grep-verified), and ValueError is
   the established service-level contract, but it is a type change on that path.
3. Sweep age validation moved inside `AssetFileStore.sweep`, so an invalid `min_age_seconds` now costs one
   SELECT before raising; exception type/message identical.
4. asset_repo.py (~500 lines) still exceeds the 200-line guidance; the phase-defined split boundary
   (file-storage vs SQL) is respected, further splitting would cut across the transaction-coordination code.
5. Phase 11 dependency: pycil pin bump (`apps/api/pyproject.toml`) still pending, per plan.

**Status:** DONE_WITH_CONCERNS
**Summary:** All seven polish items implemented and verified green (640 passed, lint-imports 5/5); asset split preserves hash-verify semantics verbatim, public names pycil consumes unchanged.
**Concerns:** stale reference in docs/codebase-summary.md (out of ownership); sense_view error-type nuance; minor sweep-validation ordering note.
