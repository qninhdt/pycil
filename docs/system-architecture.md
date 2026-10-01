> Current architecture authority: [`./design/`](./design/README.md).

# System Architecture

Pycil is a single-VPS Compose product with the web app deployed separately:

```text
Browser ── HTTPS/Caddy ── FastAPI API ── PostgreSQL (public + lexi + checkpoint)
   │            │              │
   │            │              └─ Redis (ephemeral session/cache/coordination)
   │            └─ Taskiq domain worker
   └── Vercel ── Next.js web ── bearer-authenticated direct calls to the API
```

The API owns application behavior and executes assistant turns inline, streaming
AG-UI events over SSE. The worker owns the two durable content jobs — word
generation and question supply — and refreshes the heartbeat the API's readiness
probe reads. PostgreSQL is canonical; Redis holds disposable state and is not a
source of business truth. Lexi is embedded behind `apps/api/pycil/lexicon`
and owns its isolated schema.

The browser holds a Clerk session and sends it as a bearer token; it polls the
owner-scoped job endpoint and consumes the assistant AG-UI stream. The
assistant-ui React runtime renders chat and streamed tool calls; the FastAPI
assistant keeps the LangGraph checkpoint and owner-scoped library tools.

For decisions and invariants, read `docs/design/`. For operational commands,
read the scripts in `scripts/` and `docs/disaster-recovery-runbook.md`.
