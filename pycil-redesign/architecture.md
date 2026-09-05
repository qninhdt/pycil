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
                          +---------+--------------+
                          |                        |
                  +-------+--------+       +-------+------+
                  | domain-worker |       | scheduler    |
                  | durable jobs  |       | periodic only|
                  +----------------+       +--------------+
```

Seven long-lived services: Caddy, web, API, domain worker, scheduler, Postgres,
and Redis. API, domain worker, and scheduler use one application image. Only
Caddy publishes ports.

The API executes assistant Runs inline and streams their events as SSE. A Run
that reaches an approval interrupt ends its request; resume opens a second
request. Durable content jobs return a receipt and are polled from Postgres.

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
| `auth` | Identity, tokens, refresh sessions, OAuth transaction | Product policy |
| `account` | User, plan, credit, export, deletion order | Per-domain rules |
| `hierarchy` | Node tree, readability, subtree scope | Learning state |
| `content` | Membership, dictionary reads, supply demand | Dictionary tables, grading |
| `learning` | Sessions, strength, depth, responses | Question content, authorization |
| `assistant` | Threads, Runs, graph, tools, prompt, approval | Domain rules behind its facades |
| `jobs` | Durable domain-job identity, claim, retry, interests | Job-specific meaning |
| `policy` | Shared read models and pure constants | Behaviour or domain imports |
| `ports` | Embedded-library contracts | Implementations |
| `common` | Errors, middleware, transport helpers | Domain vocabulary |
| `db` | Engines, sessions, Redis handle, model aggregator | Domain behaviour |

## 3. Dependency chain

Lower tiers may not import higher tiers. Wrong-way edges are injected.

```text
tier 4   account
tier 3   assistant
tier 2   learning · content
tier 1   hierarchy · jobs
tier 0   auth · policy · ports · common · db
```

`content` and `hierarchy` read learner-sense state from `policy`; `learning` is
its only writer. `policy` imports no domain module.

## 4. Data ownership

```text
postgres
├── public
│   ├── auth       users, identities, refresh sessions
│   ├── account    plans, credit ledger
│   ├── hierarchy  nodes, deck membership
│   ├── learning   learner-sense state, reviews, responses, summaries
│   ├── assistant  threads, runs
│   └── jobs       tasks, interests
├── assistant checkpoint schema  owned by the checkpointer
└── lexi
    └── words, senses, examples, forms, relations, questions
```

Pycil stores Lexi `sense_id` values as opaque integers without foreign keys,
never writes Lexi tables, and never joins across the ownership boundary.

## 5. Request shapes

```text
synchronous command/query
  browser -> API -> Postgres -> response

durable domain job
  browser -> API -> commit job -> best-effort enqueue -> 202 receipt
  scheduler repairs lost dispatch; browser polls GET /v1/jobs/{id}

assistant turn
  browser -> POST /v1/assistant/... -> API executes graph -> SSE frames
  interrupt -> persist checkpoint + status, close stream
  resume -> second POST -> Command(resume=...) -> SSE frames
```

The canonical read repairs every missed transport event. SSE is transient
delivery; polling reads durable job state.

## 6. Scaling seams

| Pressure | First move |
|---|---|
| HTTP or assistant concurrency | Add API replicas; admission remains per learner in Postgres |
| Domain-job backlog | Add domain workers; durable claim prevents duplicate effects |
| Periodic work | Keep one scheduler through deployment configuration |
| Redis contention | Split broker and cache instances |
| Database reads | Measure, index, then add a replica only for safe read models |

## 7. Architecture invariants

```text
only Caddy publishes ports
the browser calls FastAPI directly on the public origin
assistant execution stays in the request that created or resumed the Run
approval interrupt holds no worker slot and no open connection
domain jobs are durable in Postgres and recover from lost enqueue
Redis loss cannot erase a job, Run, or learner state
policy imports no domain module
Pycil never writes or foreign-keys into schema lexi
```
