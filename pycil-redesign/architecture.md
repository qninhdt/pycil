# architecture

Topology, module layout, dependency chain, data ownership. Decisions `A1`–`A8`.

## 1. Topology

```text
                          Browser / mobile
                            |          `-- one Centrifugo connection
                            |              WebSocket primary, SSE fallback
        HTTPS commands + queries
                            v                     v
                    +-------------------+   +--------------+
                    |      Caddy        |   |  Centrifugo  |
                    |  sole public edge |   |              |
                    +---------+---------+   +------+-------+
                              |                    ^
              +---------------+--------+           | private publish
              v                        v           |
        +-----------+          +--------------+    |
        |    web    |          |     api      |----+
        | Next.js   |          |   FastAPI    |
        |  UI only  |          |  + relay     |
        +-----------+          +------+-------+
                                      |
              +-----------------+-----+-----+------------------+
              v                 v                             v
      +---------------+  +--------------+            +------------------+
      |   postgres    |  |    redis     |            |    scheduler     |
      | public + lexi |  | streams,     |            |  periodic only   |
      +-------+-------+  | cache, coord |            +---------+--------+
              ^          +------+-------+                      |
              |                 |                             |
              |    +------------+------------+----------------+
              |    v                         v
              | +------------------+  +------------------+
              +-| domain-worker    |  |  agent-worker    |
                | jobs: word,      |  | runs only        |
                | supply, grade,   |  | own queue        |
                | reconcile        |  | own drain window |
                +------------------+  +------------------+
```

Eight processes, one image for `api` / `domain-worker` / `agent-worker` /
`scheduler`. Only Caddy publishes ports; everything else is reachable on the
internal network only.

Realtime is a **delivery layer**, never a source of truth (`A4`). A worker holds
no connection to a client, so it publishes and the client reads from the channel
it already has (`G2`).

## 2. Module layout

Flat, four files where four are needed (`A2`):

```text
module/
├── models.py     tables
├── schemas.py    request and response shapes
├── service.py    behaviour
└── router.py     routes only
```

A module that outgrows this splits by **concern**, never by architectural tier —
`session/` and `scheduling/`, not `domain/` and `infra/`.

| Module | Owns | Must never own |
|---|---|---|
| `auth` | Identity, tokens, refresh sessions, OAuth transaction | Any product concept |
| `account` | The user row, plan, credit ledger, export, deletion order | Any per-domain rule |
| `hierarchy` | The node tree, readability, structural generation, subtree scope | Learning state, dictionary content |
| `content` | Deck membership as opaque sense ids, dictionary reads, supply demand | The dictionary itself, question grading |
| `learning` | Sessions, the two axes, FSRS effects, response records | Question content, node authorization |
| `agent` | Threads, Runs, tools, prompts, approval | Any domain rule it calls through a facade |
| `jobs` | Durable task identity, lease, fence, outbox, receipts | What any job means |
| `realtime` | Connection token, subscribe authorization | The resources it authorizes |
| `policy` | Read models more than one module reads; pure constants | Any behaviour, any import of a domain |
| `ports` | Contracts consumed from the dictionary library and the realtime gateway | Implementations |
| `common` | Errors, middleware, retry | Domain vocabulary |
| `db` | Engine, session, Redis handle, model aggregator | — |

## 3. Dependency chain

Lower may not import higher. A needed edge that points the wrong way is
**injected**, not imported.

```text
tier 4   account            (deletion and export touch everything)
tier 3   agent              (calls hierarchy / content / learning facades)
tier 2   learning · content (content -> hierarchy for node access)
tier 1   hierarchy · jobs · realtime
tier 0   auth · policy · ports · common · db
```

Two edges are deliberately injected rather than imported, and both were real
cycles:

| Edge | Why injected |
|---|---|
| `realtime` needs one integer from `auth` (the current token version) while `auth` needs one function from `realtime` (disconnect a user) | One integer one way and one function the other is a cycle. The lookup is passed in as a parameter, which costs one argument and removes the edge |
| `content` and `hierarchy` both read the learner-sense row that `learning` writes | Neither is reaching into learning's internals; both want the same read-only fact. The table lives in `policy` (`A3`), and learning stays its only writer |

`policy` may import **no** domain. That constraint is what stops it becoming a
second place where behaviour lives.

## 4. Data ownership

```text
postgres
├── schema public          Pycil owns
│   ├── auth              users, refresh_sessions
│   ├── account           plan, credit ledger
│   ├── hierarchy         nodes, deck membership
│   ├── learning          learner-sense state, review log, responses, summaries
│   ├── agent             threads, runs, checkpoints
│   └── jobs              tasks, interests, events, outbox, receipts
└── schema lexi            the dictionary library owns
    └── words, senses, examples, forms, relations, questions
```

The boundary is one rule: **Pycil stores a `sense_id` as a plain integer with no
foreign key** (`A5`). Pycil never writes dictionary tables and never joins across
the boundary; the dictionary never learns that a learner exists.

Two consequences that look like defects and are not:

- A deleted sense leaves a learner-sense row pointing at nothing. Reads tolerate
  a missing sense as a state, not an error.
- Deletion cannot cascade across the boundary, which is why delete rules stay
  `NO ACTION` with hand-ordered deletion (`O11`).

Redis holds nothing canonical: session-local study state, the served-question
exclusion set, quota counters, an OAuth transaction, agent admission, the
Centrifugo engine.

## 5. Request shapes

Three, and the third is what most of this design is about.

**Synchronous.** Read a node, list a deck, answer a deterministic question. One
request, one transaction, one response.

**Asynchronous with a receipt.** Generate a word, prepare supply, grade free
text. The command commits state and an outbox row in one transaction and returns
a handle; a worker performs the work; the client learns through the channel it
already has, and can always read the canonical state over HTTP.

```text
POST  ─┐
       ├─ BEGIN  mutate + INSERT outbox  COMMIT   ──►  202 { id }
       │
relay  ├─ claim FOR UPDATE SKIP LOCKED ─► publish ─► mark
       │
worker ├─ claim, lease, fence ─► work ─► write result
       │
client └─ subscribed already; falls back to GET when the buffer is outrun
```

**Interrupted.** An agent Run that needs a human decision. The run yields inside
a node, the job ends, the checkpoint holds the state, and approval enqueues a new
job (`G10`, `G11`). A waiting decision occupies no capacity.

## 6. What scaling looks like

Per `R1`, configuration only:

| Layer | Lever | Constraint |
|---|---|---|
| `api` | replicas | Stateless. The outbox relay runs in every replica; `SKIP LOCKED` makes that safe (`F6`) |
| `domain-worker` | replicas, concurrency | Idempotent consumers (`F7`, `F8`) |
| `agent-worker` | replicas, `--max-async-tasks` | One running Run per Thread is a unique index, so replicas cannot double-run one thread (`G5`) |
| `centrifugo` | replicas | Redis engine carries cross-node fan-out; no sticky sessions (`E1`) |
| `postgres` | vertical, then a read replica | The only stateful component |

Nothing derives identity from a hostname, container name, or replica index. That
is what keeps `O1`'s "an orchestrator is a config change" true rather than
aspirational.
