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
                     | UI only  | | content tasks     |
                    +----------+ +---+------------+---+
                                       |            |
                              +--------v--+    +----v-----+
                              | Postgres |    |  Redis   |
                               | public + |    | receipts,|
                              | lexi     |    | cache,   |
                              +-----^----+    | coord    |
                                    |         +----^-----+
```

**The target is four long-lived services: Caddy, API, Postgres and Redis.**
The web app deploys to Vercel and is not a Compose service. Only Caddy
publishes ports. A migration is a one-shot service, not a sixth long-lived one.

The current `docker-compose.yml` still runs `web` and a profiled `backup`
service. Removing them is [Phase 15](../plans/260924-0608-pycil-complete-redesign/phase-15-infrastructure-and-backup.md)'s
work, gated on the local browser and WAL-G restore paths existing; until then the
repository is mid-transition and this section describes the destination.

There is no worker or scheduler process. Content tasks run after responses in
the API process, with no periodic sweep or worker heartbeat.

That choice removes the reconciliation guarantee the older design relied on, and
the implementation is honest about the consequence rather than pretending
otherwise: content-job receipts live in Redis with a 24-hour TTL and **no durable
job row exists**, so a task abandoned by an API restart is not recovered — the
learner's own retry re-requests it. See
[cross-cutting/messaging.md](./cross-cutting/messaging.md) §4.

The API executes assistant Runs inline and streams their events as SSE. A Run
that reaches an approval interrupt ends its request; resume opens a second
request. Best-effort content jobs return a receipt and are polled from the API's job
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
| `jobs` | Post-response content tasks and owner-scoped Redis receipts | Durable job rows |
| `policy` | Shared read models and pure constants | Behaviour or domain imports |
| `ports` | Embedded-library contracts | Implementations |
| `common` | Errors, middleware, transport helpers | Domain vocabulary |
| `db` | Engines, sessions, Redis handle, model aggregator | Domain behaviour |

`auth` no longer owns tokens, refresh sessions or an OAuth transaction. Clerk
signs and validates sessions; the API verifies a bearer token against Clerk's
JWKS and maps the subject to the internal UUID every product foreign key points
at. There is no local signing path and no fallback, so a Clerk outage fails
closed. See [cross-cutting/auth.md](./cross-cutting/auth.md).

`jobs` owns best-effort task receipts. There is no durable job row, no claim,
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

Content and study logic run in the same Python project. Job receipt helpers do not
start a second service or import a message broker.

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
embedded, not a service: background callbacks construct their own `Lexicon` from
settings and close it after use.

## 5. Request shapes

```text
synchronous command/query
  browser -> API -> Postgres -> response

best-effort content job
  browser -> API -> write Redis receipt -> receipt id
  after response: API background callback -> Lexi -> update receipt
  browser polls GET /v1/jobs/{id} until terminal
  an abandoned nonterminal receipt reads as expired after its deadline

assistant turn
  browser -> POST /v1/assistant -> API executes graph -> SSE frames
  interrupt -> persist checkpoint + status, close stream
  resume -> second POST -> Command(resume=...) -> SSE frames
```

The canonical read repairs every missed transport event. SSE is transient
delivery; the job receipt is the polled state.

## 6. Scaling seams

| Pressure | First move |
|---|---|
| HTTP or assistant concurrency | Add API replicas; admission remains per learner in Postgres |
| Content-job overload | Bound admission; add a broker/worker only if recovery or isolation is needed |
| Redis contention | Measure receipt/session/cache load before changing topology |
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
