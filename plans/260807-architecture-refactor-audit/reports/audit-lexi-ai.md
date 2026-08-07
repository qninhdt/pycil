# Architecture audit — lexi-ai

Repo: `/home/qninh/projects/lexi-ai` (separate from pycil; embedded via pinned git rev).
Scope: whole `lexi_ai` package, 13.3k LOC / 137 modules. Tests: 12.5k LOC / 40 modules.
Method: AST import graph over every module + read of every file cited. `import-linter` run live (5/5 contracts KEPT).

Headline: the layering is real, not theatre — but the enforcement is narrower than the design, and three
distinct clusters of leftover/ceremony sit inside an otherwise coherent structure. This library is
**over-abstracted in two specific places** (`domain/ports.py` degenerate protocols, `api.py` callable
injection) and **under-consolidated in three** (`db.py`, `vectors.py`, `read_models.py`). Net recommendation
leans toward deletion, not addition.

---

## 1. Layering reality check

`import-linter` passes all 5 contracts (verified by running it). That is genuine — the two contracts added
after the last refactor (`application depends on ports, never on infrastructure`, package-level not
module-enumerated, `pyproject.toml:150-166`) close the exact rot the file's own comment describes.

But the contracts do not cover the whole design. AST scan finds edges no contract forbids:

### Violations — `domain/` reaching outward

| Edge | Why it matters |
|---|---|
| `domain/asset_identity.py:18` → `lexi_ai.config.get_settings` | Domain reads ambient env at call time (`asset_identity.py:62`). A pure identity function's output depends on process environment. |
| `domain/asset_identity.py:25` → `normalize._CTRL_RE` | Domain imports a **private** symbol from a root module. |
| `domain/ports.py:47` → `generation.schemas` (`GeneratedEntry`, `GeneratedSense`, `GeneratedAlias`, `GeneratedTopic`, `RelatedWord`, `ExampleGenContext`) | **The strongest leak.** The persistence port is typed in terms of *pydantic LLM response models*. `WordRepo.upsert_core(entry: "GeneratedEntry")` (`ports.py:75`) means the DB write interface cannot change without the LLM output schema, and vice versa. |
| `domain/ports.py:44,55` → `read_models` (`Asset`, `Entry`, `SenseView`, `Stats`) | Ports depend on the public read model, which lives outside `domain/`. |
| `domain/ports.py:56` → `theming.schemas.ThemedResult` | Same shape as the generation leak. |

All are under `TYPE_CHECKING`, so runtime is clean and the contracts (which use `allow_indirect_imports`)
don't see them. The coupling is still real for anyone changing either side.

### Violations — `application/` reaching outward

- `application/question_ports.py:10` → `from sqlalchemy.exc import NoResultFound`. **The application layer
  imports SQLAlchemy.** The `application` contracts forbid `lexi_ai.infrastructure` and
  `infrastructure.db.models`; only the *contracts* package forbids `sqlalchemy` (`pyproject.toml:112`). Live
  gap. Root cause: `entry_repo`/`sense_repo` leak driver exceptions (§6).
- `application/enrichment.py:256-257` → `generation.schemas`, `generation.wsd` (function-local imports).
- `application/questions.py:29` → `questions.engine.QuestionEngine`; `:70,:78` runtime-import
  `questions.render.to_presented`. Application depends on the concrete questions subsystem.
- Every application module imports `read_models` (9 edges) and `normalize` (5 edges) — root-level modules
  outside the layer scheme entirely.

### Verdict on the ceremony

**Earning its keep:** the reader/engine capability split (`facades/__init__.py:1-7`) — a reader deployment
literally cannot construct a provider. The `UnitOfWork` factory-callable seam — 8 application modules take
`Callable[[], UnitOfWork]` and 540 LOC of tests (`test_services_with_fakes.py`) run the services with no
database at all. That is a paid-for abstraction.

**Cargo cult:** the six single-impl aggregate Protocols as *substitution seams* (§2), and two of them are
broken as written. `application/questions.py` is a 100-LOC service whose 4 of 6 methods are one-line
forwards to the engine (`:63`, `:90`, `:93`) — it exists to satisfy the layer diagram, and the one thing it
does add (demand-type mapping, `:33-44`) is 12 lines.

---

## 2. `domain/ports.py` — 380 LOC, port-by-port

Implementations counted by AST; test doubles by grep.

| Port | Impls | Test double | Varies at runtime? | Verdict |
|---|---|---|---|---|
| `WordRepo` (`:59`) | 1 — `SqlWordRepo` (`word_repo.py:27`) | `FakeRepo` (duck-typed, `test_services_with_fakes.py:31`) | No | **Keep as docs** — see below |
| `SenseRepo` (`:119`) | 1 — `SqlSenseRepo` (`sense_repo.py:58`) | `FakeRepo`, `RecordingSenseRepo` (`test_embed_missing_pagination.py:31`) | No | Keep as docs |
| `ThemeRepo` (`:177`) | 1 — `SqlThemeRepo` (`theme_repo.py:28`) | `FakeRepo` | No | Keep as docs |
| `TagRepo` (`:223`) | 1 — `SqlTagRepo` (`tag_repo.py:19`) | `FakeRepo` | No | Keep as docs |
| `EntryRepo` (`:241`) | 1 — `SqlEntryRepo` (`entry_repo.py:42`) | `FakeRepo` | No | Keep as docs |
| `StatsRepo` (`:251`) | 1 — `SqlStatsRepo` (`stats_repo.py:25`) | `FakeRepo` | No | Keep as docs |
| `UnitOfWork` (`:257`) | 1 — `SqlAlchemyUnitOfWork` (`uow.py:26`) | `FakeUnitOfWork` (`:56`) | No | **KEEP — load-bearing** |
| `VectorIndex` (`:284`) | **3** — `InMemoryVectorIndex`, `LanceDbVectorIndex`, plus `None` | `FakeVectorIndex` (`:468`) | **YES** — `build_vector_index` branches on settings (`infrastructure/vectors/__init__.py:41-52`) | **KEEP — the only port that earns it outright** |
| `QuestionStore` (`:320`) | 1 — `QuestionRepository` | none | No | **COLLAPSE** |
| `AssetStore` (`:343`) | 1 — `AssetRepository` | none | No | **COLLAPSE** |

Plus 3 more Protocols in `questions/base.py`, all single-impl: `QuestionStore` (`:44`),
`SenseEntryLoader` (`:66` → `application/question_ports.py:16`), `TtsPort` (`:72` →
`question_ports.py:37`).

### The two to collapse, and why

**`AssetStore` is a Protocol that types nothing.** `ports.py:362-366`:

```python
    async def put_text(self, *args, **kwargs) -> "Asset":
    async def put_file(self, *args, **kwargs) -> "Asset":
```

Two of its eight methods have erased signatures. The docstring (`:345-352`) says it exists because "the
layer's one dependency on infrastructure was a type hint" — i.e. it was created purely to satisfy the
import contract, and the two methods that were hard to restate were given `*args`. It buys nothing a
`Protocol`-free duck type wouldn't.

**`QuestionStore` is defined twice, with different method sets, over the same class.**
`domain/ports.py:320` declares `get`/`list_for_sense`/`delete`. `questions/base.py:44` declares
`insert`/`retrieve_one`/`list_for_word`/`get`/`delete`. Both are structurally satisfied by
`QuestionRepository` (6 methods). Two names, one impl, two partial views.

### Port/impl drift — a real hole

`WordRepo` does **not** declare `mark_error`, but `application/generation_writer.py:91` calls
`uow.words.mark_error(...)` through the port. The application calls a method the port doesn't have. Nothing
catches it (no mypy in `pyproject.toml`; ruff's `select = ["E","F","I","UP","B"]` won't). Silent contract
hole in the error-recording path — the least-exercised path in the writer.

`SenseRepo` declares `apply_resolutions`/`pending_relations`; `SqlSenseRepo` doesn't define them — they
arrive via `SenseRelationResolutionMixin` (`sense_relation_repo.py:39`). Correct, and the module docstring
(`:1-17`) explains the mixin-not-repo choice well. No action.

### Judgment on the remaining six

I do **not** recommend deleting the six aggregate Protocols, despite each having exactly one impl and no
Protocol-typed double. Reason: they are 380 LOC of which most is docstring, and they are the single best
description of the persistence surface in the repo — `ports.py:130-145` (`needing_embedding` explaining why
the relational store cannot filter on embeddedness) and `:147-152` (why `semantic_rows` skips rather than
raises) are invariants documented nowhere else. Deleting them saves LOC and loses the map. Keep, but stop
describing them as substitution seams — only `VectorIndex` is one.

---

## 3. The public surfaces — actually five, and pycil consumes two

| Surface | LOC | What it is |
|---|---|---|
| `__init__.py` | 80 | Re-exports `Lexicon`, both facades, 18 contract types, 8 read models, 4 functions |
| `api.py` | 285 | `Lexicon` — composition root, 10 public service accessors |
| `facades/engine.py` | 293 | 30 methods; **28 are pure single-return delegations** |
| `facades/reader.py` | 209 | 24 methods; **23 are pure single-return delegations** |
| `read_models.py` | 267 | 13 dataclasses — the dictionary DTOs |
| `contracts/questions.py` | 166 | 18 answer-safe question DTOs |

### What pycil actually imports

```
lexi_ai.contracts        → 15 files (the bulk: PresentedQuestion, PrepareDemand, Evaluation, Reveal, …)
lexi_ai                  → 4 files, exactly one symbol: Lexicon
lexi_ai.read_models      → 1 file, tests only (test_lexi_contract_parity.py:176,193)
lexi_ai.migrations       → 1 test (deployment assertion)
```

pycil never imports `lexi_ai.facades`, `lexi_ai.api`, or any internal. It calls `lexicon.reader()` /
`lexicon.engine()` and `cast()`s to its **own** structural Protocols in
`apps/api/pycil/ports/lexi.py:85-128` — which restate `SenseView`, `EntryView`, `SearchResultView`
field-by-field. So `read_models.py` is a de-facto public contract consumed *structurally*, and
`contracts/__init__.py:10-12` already admits it belongs in `contracts/`:

> Dictionary DTOs (``Entry``, ``SenseView``, ``Theme``, ``Asset``, ...) migrate into
> ``contracts/dictionary.py`` in Phase 3 [...] today they still live in ``lexi_ai.read_models``.

**One coherent API or three?** One *intended* API (`contracts` + two facades) with the dictionary half
still shipping from the wrong module. The facades themselves are coherent — the split is a capability
boundary, and 51/54 forwarding methods is the honest price of it.

### Contract mismatch worth fixing

`apps/api/pycil/ports/lexi.py:88` declares `async def get_entry(self, word_id: int) -> EntryView | None`.
Lexi's implementation raises: `SqlEntryRepo.entry` uses `.scalar_one()` (`entry_repo.py:61`) and the facade
docstring says nothing about `None` (`reader.py:77-84`). pycil survives only because
`content/router.py:143-150` wraps the call in a bare `except Exception`. The declared type is wrong on
pycil's side; the raise is undocumented on lexi's side.

### Public but unconsumed (14 methods)

`delete_asset`, `delete_tag`, `delete_theme`, `get_asset`, `get_many`, `get_status_many`,
`list_questions_for_sense`, `list_themes`, `merge_tags`, `purge_assets`, `rename_tag`, `tts_many`,
`update_theme`.

These are curation/admin surfaces with real tests behind them (`test_api.py`, `test_assets.py`,
`test_tags.py`, `test_themes.py`). A library may legitimately expose more than its one consumer uses. **Not
recommending deletion** — but they are the answer to "what can be cut if the surface must shrink", and
`get_many`/`get_status_many` in particular are batch variants of methods pycil calls singly.

---

## 4. Loose top-level modules

| Module | LOC | Importers (by layer) | Belongs in | Diagnosis |
|---|---|---|---|---|
| `read_models.py` | 267 | **26** — app 9, root 7, infra 5, domain 2, facades 2, ext 1 | `contracts/dictionary.py` | Most-depended module in the package. Migration explicitly pending per `contracts/__init__.py:10-12`. |
| `normalize.py` | 345 | **21** — root 9, app 5, infra 5, domain 1, ext 1 | `domain/` | Pure, zero deps. Defines `match_key` — the identity function the whole schema keys on. Genuinely domain. Blocker: its private `_CTRL_RE` is imported by `domain/asset_identity.py:25` **and** `infrastructure/db/sanitize.py:14` — a private crossing two layers. Promote it before moving. |
| `constants.py` | 515 | 11 — infra 6, root 3, app 1, domain 1 | split (see below) | **Dumping ground.** Lines 311-497 are `TRANSLATION_LANGUAGES`, a 180-entry ISO-639 dict = **~36% of the file**. Verified dead: `SCORE_KINDS` (`:308`) and `REL_SYMMETRY` (`:184`) have **zero** references anywhere outside their definition. `EXPOSURE_LEVEL` (`:285`) is referenced only by its own test (`test_constants.py:110`). |
| `llm.py` | 338 | 10 — root 8, infra 2 | `infrastructure/llm/` | Imports `openai` (`:186,:241`). Textbook infrastructure adapter sitting at the root, imported directly by `questions/`, `generation/`, `theming/`, `assets/`. |
| `embeddings.py` | 152 | 2 | `infrastructure/` | Lazy-imports torch/transformers. Infrastructure adapter. |
| `config.py` | 105 | 10 — root 6, infra 3, **domain 1** | root is defensible | Cross-cutting. The domain edge (`asset_identity.py:18`) is the problem, not the module's location. |
| `markup.py` | 70 | 2 (one is `__init__` re-export) | `domain/` | Pure text utility, publicly re-exported (`__init__.py:29`). Small and self-contained. |
| `db.py` | 137 | 3 — infra 2, root 1 | **fold into `infrastructure/db/`** | See below. |
| `vectors.py` | 31 | **1** | **delete** | See below. |

### `db.py` vs `infrastructure/db/` — migration leftover, and a package cycle

`db.py:23` imports `from lexi_ai.infrastructure.db.models import Asset, Base` — upward, into the package
that should own it. Meanwhile `infrastructure/db/repositories/asset_repo.py:27` and
`question_repo.py:24` import `from lexi_ai.db import session_scope` — back down.

Net: `infrastructure.db.repositories → lexi_ai.db → infrastructure.db.models`. A package-level cycle that
only survives because Python resolves it at module granularity. `db.py` holds engine construction
(`:55`), session factory (`:65`), bootstrap DDL (`:71`), a destructive assets migration (`:79`), and
`session_scope` (`:124`) — every one of those is `infrastructure/db/`'s job. Its own docstring still says
"(Phase 2)".

**Verdict: leftover.** Fold into `infrastructure/db/engine.py` + `infrastructure/db/session.py`.

### `vectors.py` vs `infrastructure/vectors/` — pure leftover

31 LOC, one function (`cosine`), **exactly one importer**:
`infrastructure/vectors/memory_index.py:13`. Nothing else in the package or tests uses it except
`tests/test_vectors.py` (37 LOC).

**Verdict: leftover.** Inline into `memory_index.py` as a module-private helper, delete the module, fold
the test.

---

## 5. `questions/` — where it lives, and whether the boundary holds

Five locations, mapped:

| Location | LOC | Contents | Boundary defensible? |
|---|---|---|---|
| `contracts/questions.py` | 166 | 18 answer-safe public DTOs | **Yes** — the answer-safety invariant is enforced by `test_contract_answer_safety.py` (131 LOC) and an import-linter contract |
| `domain/questions.py` | 74 | `GradingSpec` union, `PersistedQuestion`, `StoredQuestion` | **Yes** — this is where the answer keys live, deliberately not re-exportable |
| `questions/` | 1024 | `base` (registry+protocols), `engine`, `render`, `scoring`, `dedup`, `distractors`, `schemas`, `types/*` | Mostly |
| `application/questions.py` + `question_ports.py` | 169 | thin service + 2 adapters | **Marginal** — 4/6 service methods are 1-line forwards |
| `generation/` | 627 | entry generation, WSD | Unrelated — shares only `llm.py` |

Plus `infrastructure/question_engine_factory.py` (101) and `infrastructure/db/repositories/question_repo.py`
(193). So: **7 locations**, not 5.

### Is the per-type polymorphism a well-executed Strategy?

**The engine does not branch on type — confirmed.** `engine.py:75` iterates `REGISTRY.values()`;
dispatch is `getattr(question_type, "prepare", None)` (`:76`) and `getattr(question_type, "grade", None)`
(`:134`). `_question_type(type_id)` (`:151`) is a dict lookup. Real Strategy, and the fail-fast contract
validation in `register()` (`base.py:171-195`) is genuinely good — it rejects a level-0 type that defines
`grade` at import time.

**But the branching moved, it didn't disappear.** `questions/render.py` holds **three parallel 4-branch
chains** on `RenderKind`:

- `to_render` — `:42, :44, :49, :51`
- `to_grading` — `:66, :68, :73, :75`
- `to_reveal` — `:87, :90, :95, :97`

Adding a 6th render kind = 3 new branches in `render.py` + a payload model in `schemas.py` + a plugin. The
plugin already declares `info.render_kind`, so the projection *could* live on it.

**I reject moving it.** `render.py` is the answer-safety choke point: one module decides what a learner may
see (`to_render`), what the grader may see (`to_grading`), and what is disclosed post-grading
(`to_reveal`). Distributing that across 5 plugin modules puts the answer-leak decision in 5 places, and
answer safety is the invariant this subsystem is built around (`contracts/questions.py:1-8`). A growing
conditional chain in one audited file beats a correct-by-convention rule in five. The chain grows at
`O(render kinds)` — currently 4, and render kinds are a *presentation* vocabulary, not a per-type one, so it
grows far slower than type count.

### Smells inside `questions/`

- **`AssessmentType`/`ExposureType` Protocols (`base.py:131,150`) are documentation only.** Dispatch is
  `getattr` (`engine.py:76,134`); registration validates with `hasattr(plugin, "grade")`
  (`base.py:187,193`). Nothing type-checks a plugin against them.
- **`StoredQuestion` (`domain/questions.py:42`) is dead in production code** — 5 references, all in
  `tests/test_contract_answer_safety.py:69-83`. A dataclass kept alive by the test that asserts it exists.
- **`REGISTRY` is a module-global mutable dict** (`base.py:158`) populated by import side-effect
  (`types/__init__.py:9-13`). See §8 for why I'd leave it.
- Both `pyproject.toml:56-62` entry points **and** direct import register the same 5 built-ins; the entry
  points are documentation plus a third-party discovery path gated by allowlist (`base.py:198-213`). The
  comment says so. Fine.

---

## 6. Repository layer — 9 repos, two incompatible session models

### Convention audit

| Repo | LOC | Constructor takes | Session model | In `uow`? |
|---|---|---|---|---|
| `word_repo` | 354 | `session: AsyncSession` | shared | yes (`uow.py:56`) |
| `sense_repo` | 353 | `session` + `words` + `assets` | shared | yes (`:57`) |
| `theme_repo` | 289 | `session` | shared | yes (`:58`) |
| `tag_repo` | 181 | `session` | shared | yes (`:59`) |
| `entry_repo` | 84 | `session` | shared | yes (`:60`) |
| `stats_repo` | 64 | `session` | shared | yes (`:61`) |
| `sense_relation_repo` | 240 | mixin — uses host's `self._session` | shared | via `SqlSenseRepo` |
| **`asset_repo`** | **457** | `session_factory` + `cache_dir` (`:48`) | **owns its own, per call via `session_scope`** | **no** |
| **`question_repo`** | 193 | `session_factory` (`:34`) | **owns its own, per call** | **no** |

The split is **reasoned, not accidental** — `ports.py:10-18` states it: assets are a post-commit
best-effort cache, questions are written by plugins in their own transaction, and folding either in would
put a best-effort step inside a transaction that must not roll back because of it.

**But the split has a cost the docstring doesn't mention.** `AssetRepository` is passed *into* the unit of
work (`uow.py:36,39`) and handed to `SqlWordRepo` and `SqlSenseRepo` (`:56-57`) — a repo that owns its own
session lives inside one that shares a session. The consequence is 80 LOC of SQLAlchemy event-listener
machinery in `asset_repo.py:364-444` (`_unlink_after_commit`, `_on_commit`, `_on_transaction_end`,
`_detach_spent_listeners`, a `_spent_listeners` list) to defer file unlinks until the *caller's* transaction
commits. That complexity is downstream of the two session models meeting. It is the single most intricate
code in the repository layer, and `asset_repo.py` is the largest file at 457 LOC.

### Is `uow.py` a real Unit of Work?

**Yes, not decoration.** One session created per `__aenter__` (`uow.py:54`); six repos constructed *and
rebound to that session* on every entry (`:56-61`); `commit`/`rollback`/`flush` delegate to it
(`:80-87`); `__aexit__` rolls back on exception and closes (`:70-78`). `session` raises if accessed outside
the context (`:45-47`). Repos genuinely compose into one transaction — `generation_writer.py:62-79` writes
words + aliases + senses + tags across four repos in a single commit, which is the whole point.
`new_session()` (`:49`) is a documented escape hatch for post-rollback error recording.

### Mapper duplication

`mappers.py:1-11` claims to be "the single home for ORM to domain to read-model translation" and warns the
sense view previously drifted across three copies. That claim is **now false** — read models are also
constructed in:

- `asset_repo.py:448` → `Asset` (and again in `application/assets.py:98` for the empty-text placeholder)
- `stats_repo.py:46` → `Stats`
- `application/dictionary.py:186` → `SearchResult`
- `application/search.py:143` → `SemanticHit` + a second inline `SenseView` (`:148-155`)
- `application/themes.py:28` → `Theme` (with a comment at `:22-27` explaining why it moved out)

Five extra sites. Most are defensible — `Theme`'s move is documented, `Stats` and `SearchResult` are
projections from `NamedTuple` rows, not ORM entities. The one that matters: `application/search.py:148-155`
builds a `SenseView` with `pos=None, cefr_level=None` while `mappers.py:104-140` builds the full 20-field
version. **That is the exact drift pattern the mappers docstring was written to prevent, reintroduced in a
different layer.** A caller reading `SemanticHit.sense.pos` gets `None` unconditionally.

### Error handling — no domain boundary

No repository raises a domain error. `entry_repo.py:61` uses `.scalar_one()`, which raises SQLAlchemy's
`NoResultFound`. That propagates through `DictionaryService.entry` to the facade and out to pycil, and it
forces `application/question_ports.py:10` to `import sqlalchemy.exc` to catch it (`:32-33`). One missing
domain error causes the application layer's only SQLAlchemy dependency.

---

## 7. AI-patchwork smells — inventory

**Duplicate abstraction**
- `db.py` vs `infrastructure/db/` — package cycle, §4
- `vectors.py` vs `infrastructure/vectors/` — 1 importer, §4
- `QuestionStore` defined twice with different method sets — `domain/ports.py:320`, `questions/base.py:44`
- Question schema knowledge in 4 places: `contracts/questions.py` (public DTOs), `domain/questions.py`
  (grading specs), `questions/schemas.py` (pydantic payload validators), `constants.py:270-286`
  (vocabularies re-validated in `question_repo.py:143-154` *and* `base.py:171-178`)
- Test module naming: `test_repository.py` (485) **and** `test_repositories.py` (584);
  `test_themes.py` **and** `test_theming.py`; `test_vectors.py` **and** `test_vector_index.py`

**Forwarding-only abstractions**
- `facades/engine.py`: 28/30 methods are single-return delegations; `facades/reader.py`: 23/24
- `AssetStore.put_text`/`put_file` typed `*args, **kwargs` (`ports.py:362,365`)
- `ProviderRegistry.questions_llm()` (`providers.py:81`) and `judge_llm()` (`:86`) both `return
  self.structured_llm()` — two names, identical bodies, no divergence
- `application/questions.py` — 4/6 methods forward to the engine

**Single-use helpers**
- `application/tags.py` — 42 LOC, 3 methods, each a 4-line `async with uow` + one repo call + commit
- `domain/hashing.py` — 15 LOC, one function, 2 importers
- `EnrichmentService.resolve_relations` (`:225`) → `self.resolve(batch_size, word_ids=None)`. One line.

**Growing conditional chains**
- `render.py` — 3 parallel 4-branch `RenderKind` chains (§5)
- `build_vector_index` (`infrastructure/vectors/__init__.py:41-52`) — 4 branches; this one is correct
  (settings-driven factory, the documented extension point)

**Constants dumping ground**
- `constants.py` 515 LOC, ~36% one ISO-639 dict; `SCORE_KINDS` and `REL_SYMMETRY` verified dead

**Boolean behavior flags** — searched; the pattern is largely absent. `questions(*, providers: bool)`
(`api.py:267`) is the one instance, and it selects a *capability context* (which providers the engine
holds), not a behavior branch inside one path. Keyword-only, documented. Not a smell.

**Callable-injection sprawl — the worst of it**
`api.py` wires services by passing bound methods of *other services*:

- `GenerationService.__init__` takes **11 arguments**, 6 of them callables (`generation.py:30-43`)
- `EnrichmentService` takes 8, 4 callable (`enrichment.py:40-50`)
- `ThemeService` takes 6, 3 callable (`themes.py:39-47`)
- `AssetService` takes 6, 3 callable (`assets.py:24-32`)

And three private adapter methods exist purely to break a construction cycle
(`api.py:198-206`), with the comment:

> passing bound methods of freshly built services would recurse forever at construction time

`_read_senses` and `_read_status` carry `# noqa: ANN001, ANN202` — untyped, unannotated. Four service
constructor params are annotated `# noqa: ANN001` with a prose comment instead of a type
(`generation.py:34-35`, `search.py:31-32`, `enrichment.py:43`). **This is where the abstraction stops
paying**: the indirection is real (six services genuinely don't import each other) but the price is
untyped seams, a documented construction cycle, and 11-arg constructors.

---

## 8. Pattern opportunities — and rejections

### Accepted

**A1 — Delete `AssetStore` and `domain.QuestionStore`; type the application against the concrete repos'
duck shape.**
(a) Problem: two Protocols exist only to satisfy the import contract. (b) Current is bad: `AssetStore`
erases two signatures to `*args, **kwargs` (`ports.py:362,365`) — a type hint that types nothing;
`QuestionStore` is one of two same-named Protocols over one class. (c) Pattern: remove the indirection —
the application already receives these by constructor injection (`assets.py:26`, `questions.py:53`), which
is the actual seam. (d) Trade-off: loses the *name* documenting what the app uses of each repo. (e) Beats
the simpler fix (repairing the signatures) because repaired signatures would just restate
`AssetRepository`'s — a one-impl Protocol whose methods exactly mirror the impl is a rename, not a boundary.

**A2 — Add `mark_error` to `WordRepo`.**
Live contract hole: `generation_writer.py:91` calls it through the port. One-line fix. Do it regardless of
everything else.

**A3 — Fold `db.py` into `infrastructure/db/`; delete `vectors.py`.**
Breaks the `infrastructure.db → db → infrastructure.db.models` package cycle; removes a 31-LOC module with
one importer. Pure deletion/relocation, no new abstraction.

**A4 — Split `constants.py`; delete `SCORE_KINDS` and `REL_SYMMETRY`.**
Move `TRANSLATION_LANGUAGES` (185 lines) to `constants/languages.py` or a data file. Leaves ~330 LOC of
actual controlled vocabularies, which is a coherent module.

**A5 — One domain error at the entry-read boundary.**
`entry_repo.py:61` `.scalar_one()` → raise a domain `EntryNotFound`. Removes the application layer's only
`sqlalchemy` import (`question_ports.py:10`) and fixes the pycil `-> EntryView | None` mismatch (§3) by
making the contract explicit either way. One error class, two call sites. This is the narrow version — I am
**not** proposing a domain-error hierarchy across all 9 repos.

**A6 — `read_models.py` → `contracts/dictionary.py` with a re-export shim.**
Finishes the migration the code already documents. **Touches the surface pycil consumes** — see §9.

**A7 — Fix `SemanticHit`'s inline `SenseView`.**
`application/search.py:148-155` builds a 6-field `SenseView` where `mappers.py:104` builds 20. `pos` and
`cefr_level` are hardcoded `None`. Either hydrate through `uow.entries.sense_views` or document that
`SemanticHit.sense` is a partial view. Currently it silently lies.

### Rejected — in favour of simplicity

**R1 — Do NOT move render/grading projection onto the plugins.** Full reasoning in §5. The 3 conditional
chains are the answer-safety choke point; distributing them multiplies the leak surface by 5. Chain grows
with *render kinds* (4), not type count.

**R2 — Do NOT replace the global `REGISTRY` with an injected registry object.**
`base.py:158` is module-global mutable state populated by import side-effect — textbook justification for
DI. Reject anyway: 5 built-ins, third-party discovery already gated by an explicit allowlist
(`base.py:198-213`), and `QuestionEngineFactory` already caches per capability context
(`question_engine_factory.py:54-62`). Injecting it threads a parameter through engine → service → facade →
`api.py` for zero behavior change. The one real cost is test isolation, and the tests already cope
(`test_registry.py`, 215 LOC).

**R3 — Do NOT fold `asset_repo`/`question_repo` into the unit of work.**
The exclusion is verified by design intent at `ports.py:10-18`: both are best-effort steps that must not be
able to roll back a committed publish. An audit arguing "consistency" brings no new evidence against a
documented invariant. The *complexity* it causes (`asset_repo.py:364-444`) is real, but it is the price of a
correct choice, not a symptom of a wrong one.

**R4 — Do NOT delete the six aggregate Protocols.** §2. Best persistence documentation in the repo; only
`VectorIndex` is a genuine substitution seam, but documentation is a legitimate reason to keep a file.

**R5 — Do NOT introduce a Facade/Command layer to shrink the 51 forwarding methods.**
The forwarding *is* the capability boundary. Any scheme that removes it (dynamic `__getattr__`, generated
delegates, a command bus) trades 500 LOC of boring, greppable, individually-docstringed methods for
machinery that defeats IDE navigation and static analysis on the *public API*. Boring wins here.

**R6 — Do NOT unify the two question-payload validation paths.**
`question_repo.py:143-154` and `base.py:171-195` both check the same vocabularies. Looks like duplication;
isn't — one validates at the persistence boundary (any draft, from any plugin), the other at registration
(plugin declarations, once at import). Different inputs, different times.

### The over-abstraction verdict

Asked plainly: **this library is over-abstracted in exactly two places.**

1. `domain/ports.py` — 12 Protocols across 2 files, **1** of which (`VectorIndex`) has multiple runtime
   implementations. Two are broken as written.
2. `api.py`'s callable injection — 11-arg constructors, 6 untyped `# noqa: ANN001` seams, three private
   adapter methods to break a documented construction cycle (`api.py:198-206`).

Everywhere else the structure is proportionate, and in several places (the reader/engine split, the
single-flight lock refcounting at `single_flight.py:41-66`, the fence-before-provider-call ordering at
`generation_writer.py:6-10`, `render.py`'s answer-safety centralization) the abstraction is doing load-
bearing correctness work with the reasoning written down. The docstrings in this codebase explain *why* at a
standard well above average; the failures are structural leftovers and two degenerate protocols, not
confused thinking.

---

## 9. Effort / risk / coverage

**Legend:** Surface = does it change what pycil consumes → coordinated two-repo re-pin.

| # | Proposal | Size | Regression risk | Existing coverage | **Changes pycil surface?** |
|---|---|---|---|---|---|
| A2 | Add `mark_error` to `WordRepo` | **S** | none (annotation only) | `test_repository.py`, `test_generation.py:385` exercise the error path | **No** |
| A4 | Split `constants.py`, delete 2 dead constants | **S** | none — verified zero refs | `test_constants.py` (118) imports `EXPOSURE_LEVEL`; update it | **No** |
| A3b | Delete `vectors.py`, inline `cosine` | **S** | none — 1 importer | `test_vectors.py` (37) — fold into `test_vector_index.py` | **No** |
| A7 | Fix `SemanticHit.sense` partial view | **S** | **low-med** — changes returned field values | `test_api.py` semantic tests; pycil has no `semantic_search` call site | **No** (behavior-visible if pycil adopts it later) |
| A1 | Delete `AssetStore` + `domain.QuestionStore` | **S/M** | low — removes annotations, no runtime change | `test_assets.py` (867), `test_question_repository.py` (166) | **No** |
| A5 | Domain error at entry-read boundary | **M** | **medium** — changes the exception type crossing the boundary | `test_api.py` (1314), `test_repositories.py` (584) | **Behaviorally yes** — pycil's `except Exception` (`content/router.py:149`) still catches it, and its `-> EntryView \| None` is already wrong. Coordinate the port fix. **FLAG** |
| A3a | Fold `db.py` into `infrastructure/db/` | **M** | medium — **19 test modules import `lexi_ai.db`** | Heavy: `test_db.py`, `test_uow_transaction.py` (215), `conftest.py:30`, `test_postgres_integration.py` (323) | **No** — pycil never imports `lexi_ai.db` |
| A6 | `read_models.py` → `contracts/dictionary.py` | **M/L** | low **with** a re-export shim; high without | 11 test modules import `lexi_ai.read_models` | **YES — LOUD FLAG.** pycil imports it at `apps/api/tests/content/test_lexi_contract_parity.py:176,193`, and its structural Protocols (`apps/api/pycil/ports/lexi.py:20-83`) mirror these dataclasses field-by-field. A shim keeps it non-breaking; **removing** `lexi_ai.read_models` requires a coordinated re-pin. |
| — | Fix pycil's `get_entry` return type | **S** | none | `content/router.py:143-150` already defensive | **pycil-side only** — but it is the pycil half of A5 |

### Coverage notes

- Overall the suite is strong: 12.5k test LOC against 13.3k package LOC, hermetic SQLite by default with an
  opt-in Postgres tier that **fails loudly rather than skipping silently** in CI
  (`conftest.py:52-56`, `LEXI_REQUIRE_PG=1`). That guard is unusually good practice.
- Weakest-covered areas relative to size: `asset_repo.py`'s deferred-unlink event machinery
  (`:364-444`) — the most intricate code in the repo; and `application/questions.py`'s forwarding methods,
  which are covered only transitively.
- `pyproject.toml` has **no type checker**. `ruff` selects `E,F,I,UP,B` only. The `WordRepo.mark_error`
  hole (§2) is exactly the class of defect mypy would catch, and several `# noqa: ANN001` markers suggest a
  stricter config was once intended.

### Suggested sequencing

Independent and safe first: **A2, A4, A3b** (all S, no surface impact, no cross-repo coordination).
Then **A1, A7**. Then **A3a** (test-heavy but internal). **A5 + pycil's `get_entry` type** as one
coordinated pair. **A6 last**, shim-first, and only with pycil re-pin scheduled.

---

## Unresolved questions

1. **`domain/ports.py` typed in terms of `generation.schemas`** (`ports.py:47`) is the deepest structural
   leak found, and I have no non-invasive fix. Decoupling means a domain-owned write DTO per aggregate plus
   generation→domain mapping — L-sized, touching every repo and the writer. Is that in scope, or is the
   coupling accepted because generation is the only writer?
2. **Are the 14 unconsumed public methods (§3) intended library surface, or accumulated?** Deleting them
   halves the facade forwarding; keeping them is defensible for a library. Needs the owner's intent, not my
   inference.
3. **Was a type checker deliberately dropped?** Several `# noqa: ANN001/ANN202` markers imply one existed.
   Whether to reintroduce mypy changes the value of A1/A2 substantially — under mypy the Protocols become
   enforcement, not documentation.
4. **`api.py` callable injection (§7)** — I can name the cost precisely but not the intended fix without
   knowing whether the six-service decomposition is itself negotiable. A single mediator/context object
   would fix the arg counts and the construction cycle at once, but that is a design decision above an
   audit's pay grade.
5. **`asset_repo.py`'s 80-LOC deferred-unlink machinery** — is orphaned-file leakage on rollback actually
   observed in production, or was this written defensively? If defensive, a periodic GC sweep replaces it
   with ~15 LOC. Needs operational evidence I do not have.
