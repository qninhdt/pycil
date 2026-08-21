# Audit Report — lexi-ai (branch redesign/defect-repair-and-ports)

Auditor: Explore agent, 2026-08- pycil integration notes by controller, 2026-08-21.

## Verdict

Ports-and-adapters redesign substantially complete and honestly enforced: 5/5 import-linter contracts pass (138 files, 437 deps, 0 broken), application/domain runtime-clean of infrastructure. Remaining work is polish, not redesign.

## Module Map (LOC)

domain 757 (ports.py 393 Protocols incl. UnitOfWork/VectorIndex/AssetStore; models; errors) · application 1,664 (dictionary/search/generation 254/generation_writer/enrichment 311/themes 216/tags/assets/questions/question_ports/single_flight/batching) · infrastructure/db (models.py 580, uow.py, mappers, sanitize, asset_gc, repositories ×9) + providers.py lazy factory 177 + question_engine_factory + vectors/ · references/ (cambridge 442 ro SQLite + wordnet nltk) · generation/ (generator, schemas 404, wsd) · theming/ · questions/ (plugin registry base.py 189 + engine dispatcher + 5 self-registering plugins) · facades/ (reader 212 + engine 297) · contracts/ (answer-safe DTOs) · assets/ (translate/tts) · migrations/ (Alembic owns Postgres lexi schema) · root: api.py 286 composition root, normalize.py 357 THE invariant, constants.py 499, llm.py 351 StructuredLLM port+adapter, read_models.py, embeddings.py 152, db.py, vectors.py, config.py.

## Intended vs Actual

Code matches documented ports/adapters design closely. Deviations: root modules blur layers (`db.py` imports infrastructure.db.models; llm/embeddings adapters at root); doc drift (system-architecture.md lists moved files); `application → generation` coupling (enrichment lazy-imports generation.schemas/wsd; GenerationWriter.publish takes GeneratedResult) uncovered by contracts; no contract forbids `sqlalchemy` in application (question_ports.py:5 imports NoResultFound).

## Keep List (do not refactor)

normalize.match_key invariant; contracts/ answer-safe DTOs; generation_writer three-deliberate-transactions; vector eventual-consistency design (None-as-off, overfetch+hydrate, orphan pruning); prompt-injection guard (llm.py:34-79); portable-type ORM; per-call service rebuild in api.py.

## Smells → Refactor Targets

| # | Finding | Evidence |
|---|---|---|
| L1 | AssetStore port under-specified: `put_text(*args, **kwargs)` | domain/ports.py:372-377 vs typed impl asset_repo.py:111-119,193-199 |
| L2 | Misnamed adapter in application: `application/question_ports.py` docstring says "Adapter", imports sqlalchemy.exc.NoResultFound (:5) | move SenseEntryLoader to infrastructure; translate NoResultFound at repo edge (SenseRepo.word_id_for → return `int \| None` like sibling reads) |
| L3 | Duplicated source dispatch `_resolve_source` vs `_anchor` | generation.py:105-127 vs :162-172 |
| L4 | Generator constructor-shell duplication ×5 | generator.py:23-42, theming/generator.py:32-48,124-129, wsd.py:5-61, translate.py:38-43 — cosmetic, lowest priority |
L5 | asset_repo.py 773 lines: query repo + file I/O + hashing + GC | split file-storage concern from SQL repo; AssetStore port unchanged |
| L6 | Docs drift: system-architecture.md:77-78,89 lists moved files; prompts location | sync docs |
| L7 | Error hierarchy split: EmbeddingUnavailable defined in embeddings.py:33; themes raises plain ValueError ×7 | relocate/typed errors |
| L8 | PrepareReport leak: exported from internal questions.base on public surface | `lexi_ai/__init__.py:71` |
| L9 | UoW repo cross-wiring (repos hold siblings + assets) | uow.py:56-57 — document or tidy, low priority |
| — | Boolean flags (force/overwrite/providers) | keyword-only, load-bearing, keep |

## Integration Notes (controller-verified)

- pycil pins lexi-ai at immutable SHA `fbbea3d…` (`apps/api/pyproject.toml:22`) = current tip of redesign/defect-...-ports; worker receives Lexi through pycil-api (single-pin policy, worker pyproject comment).
- Any lexi-ai change consumed by pycil requires: commit in lexi repo → verify lexi suite + lint-imports → bump pin SHA in apps/api/pyproject.toml + uv lock → run api+worker suites.
- pycil consumes via `pycil/ports/lexi.py` Protocols; import-linter forbids pycil domain → lexi_ai.
