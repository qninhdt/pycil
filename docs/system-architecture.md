# Backend architecture

The current backend has five business modules: `account`, `vocabulary`, `library`,
`study`, and `assistant`, plus explicit root runtime/migration infrastructure and
one `worker.py`. `apps/web` is intentionally absent. Older material in
`docs/design/`, journals, plans and root analysis reports describes prior designs,
not the implemented runtime.

```text
Client ── Caddy ── FastAPI API ── PostgreSQL
                         │        public: Pycil account/library/memory/events
                         │        lexi: native dictionary/Questions
                         │        checkpoints: native LangGraph durability
                         └────── Redis: assistant leases/start limits, actor/deck caches
Generation worker ── native Lexi generation + assistant retention
```

- Client owns learning sessions, rounds, exposures, answers, navigation, resume and
  K-answer aggregation. Server preparation is read-only and returns complete
  K-question bundles in due → new → future order, with honest smaller counts.
  Native allocation can select multiple questions of the same type.
- One user–Sense memory spans decks. Each trusted rating uses server arrival time,
  native FSRS and a minimal retry-safe event. Early positive ratings log practice
  without touching memory; early AGAIN applies FSRS. No answer/result store exists.
- Native grading returns diagnostic objects, including null fields, without a
  generated verdict/feedback/rating or an invented advanced-grading unit debit.
- Shared work has unique `(available_id, target)` identity from explicit client
  selection. One advisory-lock-owning worker fills missing neutral banks to eight
  Questions per native type/Sense. Generation never searches or debits a user.
- Assistant uses native LangChain agents, AG-UI streams/HITL and PostgreSQL
  checkpoints. Admission occurs before response start. Destructive actions require
  approval and live authorization. Locks/settlement release safely on cancellation;
  pending approval releases the execution slot and rejection requires no new call.
  `POST /v1/assistant` streams uncompressed SSE through Caddy; conversation GET
  projects native messages and persisted approval IDs for reload/resume.
- Editor saves apply final metadata/membership in one atomic PUT. Deck previews are
  unpaginated; folder/reference scopes remain paginated. Lexi owns shared Tantivy
  search and lexical/artifact caches. Live authorization and user memory are not
  cached as shared lexical/deck facts.
- Subscription allowances, token-unit weights, type/format levels, bounds and
  retention are validated from `config/config.yaml`. Deployment addresses/secrets
  come from the environment. Imports do not read YAML or open connections.
- The explicit migration gate runs Lexi → Pycil → checkpoint setup → verification.
  API/worker startup only verifies schema versions. It never repairs/migrates.

See [testing](testing-setup.md), [current frontend contract](frontend-backend-contract.md) and
[packaged dependency provenance](../vendor/lexi-ai/README.md). Operational reset or
deployment needs an exact target and separate approval; historical runbooks must
not be used against this schema.
