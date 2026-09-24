# architecture

Topology, module layout, dependency chain, data ownership. Decisions `A1`–`A8`.

## 1. Topology

```text
                         Browser / mobile
                    HTTPS, SSE, authenticated polling
                                 |
                         +-------v-------+
                         |     Caddy     |
                         | public edge   |
                         +---+-------+---+
                             |       |
                    +--------v--+ +--v----------------+
                    | Next.js  | | FastAPI API       |
                    | UI only  | | assistant inline  |
                    +----------+ +---+------------+---+
                                       |            |
                              +--------v--+    +----v-----+
                              | Postgres |    |  Redis   |
                              | public + |    | streams, |
                              | lexi     |    | cache,   |
                              +-----^----+    | coord    |
                                    |         +----^-----+
                                    |              |
                                    +--------------+
                                           |
                                  +--------+--------+
                                  |  domain-worker  |
                                  | durable jobs +  |
                                  | heartbeat loop  |
                                  +-----------------+
```

**The target is five long-lived services: Caddy, API, domain worker, Postgres and
Redis.** The web app deploys to Vercel and is not a Compose service. API and
domain worker are separate commands from one application image. Only Caddy
publishes ports. A migration is a one-shot service, not a sixth long-lived one.

The current `docker-compose.yml` still runs `web` and a profiled `backup`
service. Removing them is [Phase 15](../plans/260924-0608-pycil-complete-redesign/phase-15-infrastructure-and-backup.md)'s
work, gated on the local browser and WAL-G restore paths existing; until then the
repository is mid-transition and this section describes the destination.

**There is no scheduler process.** Earlier revisions of this folder specified one
(`F9`) to own heartbeat, dispatch reconciliation and retention sweeps. The
implemented worker owns its own liveness: `pycil_worker/main.py` starts
`_heartbeat_loop` as an in-process task and refreshes `worker:heartbeat`, which
is the key API readiness reads. Nothing sweeps periodic work.

That choice removes the reconciliation guarantee the older design relied on, and
the implementation is honest about the consequence rather than pretending
otherwise: content-job receipts live in Redis with a 24-hour TTL and **no durable
job row exists**, so a lost publication is not recovered by anything — the
learner's own retry re-requests it. See
[cross-cutting/messaging.md](./cross-cutting/messaging.md) §4.

The API executes assistant Runs inline and streams their events as SSE. A Run
that reaches an approval interrupt ends its request; resume opens a second
request. Durable content jobs return a receipt and are polled from the API's job
route, which reads that Redis receipt.

## 2. Module layout

```text
module/
├── models.py
├── schemas.py
├── service.py
└── router.py
```

Modules split by concern when needed, never by generic architectural tiers.

| Module | Owns | Must never own |
|---|---|---|
| `auth` | Clerk bearer verification, subject→internal-UUID mapping, the `users` row | Sessions, refresh state, product policy |
| `account` | User plan, credit ledger, period roll, export, deletion order | Per-domain rules |
| `hierarchy` | Node tree, readability, subtree scope, small cache generations | Learning state |
| `content` | Membership, dictionary reads, supply demand | Dictionary tables, grading |
| `learning` | Sessions, strength, depth, responses | Question content, authorization |
| `assistant` | Threads, graph, tools, prompt, approval | Domain rules behind its facades |
| `queue` | Content-job publication, the owner-scoped Redis receipt | Durable job rows |
| `policy` | Shared read models and pure constants | Behaviour or domain imports |
| `ports` | Embedded-library contracts | Implementations |
| `common` | Errors, middleware, transport helpers | Domain vocabulary |
| `db` | Engines, sessions, Redis handle, model aggregator | Domain behaviour |

`auth` no longer owns tokens, refresh sessions or an OAuth transaction. Clerk
signs and validates sessions; the API verifies a bearer token against Clerk's
JWKS and maps the subject to the internal UUID every product foreign key points
at. There is no local signing path and no fallback, so a Clerk outage fails
closed. See [cross-cutting/auth.md](./cross-cutting/auth.md).

`queue` replaced the older `jobs` module. There is no durable job row, no claim,
no attempt counter and no interest table — the receipt is a Redis record with a
24-hour TTL. See [cross-cutting/messaging.md](./cross-cutting/messaging.md).

## 3. Dependency chain

Lower tiers may not import higher tiers. Wrong-way edges are injected.

```text
tier 4   account
tier 3   assistant
tier 2   learning · content
tier 1   hierarchy · queue
tier 0   auth · policy · ports · common · db
```

`content` and `hierarchy` read learner-sense state from `policy`; `learning` is
its only writer. `policy` imports no domain module. `queue` is dependency-free by
design — it is imported by both the API and the worker, so importing Taskiq there
would drag the broker into the API's request path.

## 4. Data ownership

```text
postgres
├── public
│   ├── auth       users
│   ├── account    user_credits, credit_debits
│   ├── hierarchy  nodes, deck_senses
│   ├── learning   user_sense_stats, review_log, responses,
│   │              user_learning_settings, session_summaries
│   └── assistant  assistant_threads
├── assistant checkpoint schema  owned by the checkpointer
└── lexi
    └── words, senses, examples, forms, relations, questions
```

`user_sense_stats` is the one learner-sense row: it lives in the `policy`
package's module but is the single progress identity across every deck holding a
sense, which is why `content` and `hierarchy` read it and only `learning` writes
it.

Pycil stores Lexi `sense_id` values as opaque integers without foreign keys,
never writes Lexi tables, and never joins across the ownership boundary. Lexi is
embedded, not a service: the API and worker each construct a `Lexicon` from
settings.

## 5. Request shapes

```text
synchronous command/query
  browser -> API -> Postgres -> response

durable content job
  browser -> API -> write Redis receipt -> best-effort publish -> receipt id
  browser polls GET /v1/jobs/{id} until terminal
  a failed publish is recorded failed, never left queued

assistant turn
  browser -> POST /v1/assistant/ag-ui -> API executes graph -> SSE frames
  interrupt -> persist checkpoint + status, close stream
  resume -> second POST -> Command(resume=...) -> SSE frames
```

The canonical read repairs every missed transport event. SSE is transient
delivery; the job receipt is the polled state.

## 6. Scaling seams

| Pressure | First move |
|---|---|
| HTTP or assistant concurrency | Add API replicas; admission remains per learner in Postgres |
| Content-job backlog | Add workers; they join the same Taskiq consumer group |
| Redis contention | Split broker and cache instances |
| Database reads | Measure, index, then add a replica only for safe read models |

There is no periodic-work seam, because there is no periodic work. A future
scheduler would be a new process, and [cross-cutting/messaging.md](./cross-cutting/messaging.md)
records what it would have to own.

## 7. Architecture invariants

```text
only Caddy publishes ports
the browser calls FastAPI directly on the public origin
assistant execution stays in the request that created or resumed the Run
approval interrupt holds no worker slot and no open connection
Redis loss can erase an unclaimed content job; the learner's retry recovers it
policy imports no domain module
Pycil never writes or foreign-keys into schema lexi
```

The fourth line is weaker than earlier revisions claimed. Because the receipt
lives in Redis with no durable row behind it, a Redis loss does lose in-flight
content work. That is the accepted trade rather than an oversight: a lost
generation is retryable from the UI, and graded learning never depends on a job.
See [cross-cutting/messaging.md](./cross-cutting/messaging.md) §4.
