# Historical design collection

These documents predate the revision-3 backend rewrite and are retained as history,
not current architecture authority or operator instructions. Current behavior is
documented in [system architecture](../system-architecture.md),
[codebase summary](../codebase-summary.md) and
[execution checkpoint](../backend-rewrite-status.md).

# Pycil Redesign (historical)

Historical target design for Pycil; superseded by the revision-3 rewrite contract.

`docs/` and `plans/` stay in the tree as a record of what was built and how. They
are inputs and history, never authority.

Created 2026-09-04.

## 1. Why this exists

The previous design lived in five root documents totalling 5,195 lines
(`notes.md`, `agent.md`, `learning-system.md`, `DESIGN.md`, `prompt.md`), a
`docs/` tree, and 33 plan directories. They contradicted each other, declared each
other superseded in place, and described mechanisms that no longer exist. Three
documents formed a precedence chain with no single authority.

This folder resolves that by **precedence, not deletion**. `docs/` and `plans/`
remain: they record what was actually done, and a record that disagrees with the
current design is still evidence about how the code reached its present shape. They
are simply no longer authority. The five root design documents are retired, since
their whole purpose was to be the authority this folder now is.

Measured baseline of the current codebase:

| Metric | Current |
|---|---|
| API production LOC / files | 12,170 / 115 |
| API test LOC / files | 13,749 / 93 |
| Worker production / test LOC | 916 / 1,637 |
| Web app LOC | 20,200 |
| Web test + story LOC / files | 8,448 / 50 |
| Alembic revisions / LOC in `versions/` | 25 / 1,805 |
| Meta-tooling scripts / baseline JSON | 1,883 LOC / 269 LOC |
| Documentation LOC (docs tree + root five + plans) | 59,832 |

Test code is roughly equal to production code in the API and 1.79× in the
worker. That is not thorough testing; it is a verification program.

**The overengineering is in the operational and verification layers, not in the
product.** The node tree, the FSRS engine, the shared dictionary, the durable
task substrate, and the auth rotation are the value.

## 2. What Pycil is

A specialised English-vocabulary tutor. The system supplies the content; the
learner supplies only the words they want.

Selling points, in order:

1. **Question diversity from two sources** — rule-based transforms of a
   normalised dictionary entry, plus AI generation where a template cannot
   reach. Delivered along a five-level retrieval-demand ladder.
2. **Agent** — a conversational agent with tools over the learner's own
   library, with human approval on destructive actions.
3. **Node tree** — nested folders, decks, and live references to another
   owner's deck. Progress is global per `(learner, sense)`, so the tree is a
   path, never an identity.

Not a general memorisation tool. Every comparison against a card-based product
is a comparison Pycil wins by giving up generality.

## 3. Target shape

One FastAPI application that executes assistant turns inline and content jobs
after responses, Postgres, Redis, and Caddy. Next.js is UI only and deploys to Vercel. Docker
Compose on one VPS, one environment. See [architecture.md](./architecture.md).

**Status.** The redesign was executed as
[an 18-phase plan](../plans/260924-0608-pycil-complete-redesign/plan.md). Phases
1–13 are complete and verified. Phase 14 (browser journeys) is blocked on a Clerk
test instance; Phases 15–16 (Vercel, WAL-G, CI) and 18 (production promotion) are
outstanding. Where this folder and the code disagree, **the code is what runs** —
the divergence is recorded in each document rather than smoothed over.

## 4. Rules every document here follows

### R0 — This is a redesign, not a bug fix

Design from requirements. The existing codebase is read **only to understand the
business domain**, never as a starting point to patch.

Consequences:

- No document here lists bugs in current code.
- No decision is justified by "the current code does X".
- A mechanism that exists in code but has no reason in this folder is **not part
  of the design**, whatever the code does today.
- This folder is **self-contained**. Nothing load-bearing may cite a document
  outside it — not because those documents disappear, but because a design that
  depends on history is a design that cannot be read on its own.

### R1 — Scale from MVP; DevOps changes config, not code

API replicas may serve requests without sticky sessions. Content tasks are
best-effort and share each API process; they do not provide durable replay or a
separately scalable worker pool. If that becomes necessary, add a real broker and
worker rather than claiming the current design already provides them.

### R2 — Every MVP choice leaves an upgrade seam

No decision may lock the system out of a later upgrade — a different broker, a
second Postgres, Kubernetes, an observability stack, a fitted FSRS weight set.
Each decision in [decisions.md](./decisions.md) carries an explicit seam.

### R3 — No overengineering

Cut anything whose cost exceeds its value for a solo developer on one VPS.
See [removed.md](./removed.md).

### R4 — No underengineering

This is not a toy. Capabilities that may **not** be cut are named per module and
enforced by the invariant checklist in [ops/testing.md](./ops/testing.md).

### R5 — Every decision carries a reference

| Tier | Source |
|---|---|
| 1 | RFC, W3C, official specification, peer-reviewed paper |
| 2 | Official documentation of the tool in question |
| 3 | Engineering guidance from an organisation operating at real scale; a recognised book |

**If a decision has no tier 1–3 source it is labelled `judgment` and the
reasoning is stated inline.** A number that must be measured is never presented
as a standard; it is named with its constraint and marked `uncalibrated`.

## 5. How to read this

Start with [decisions.md](./decisions.md) — the index of every decision with
rationale, reference, and upgrade seam.

| Then | For |
|---|---|
| [architecture.md](./architecture.md) | Topology, module layout, data ownership |
| `modules/*` | What each module owns and must never own |
| `cross-cutting/*` | Concerns spanning modules |
| `ops/*` | Deployment, CI, testing |
| [removed.md](./removed.md) | What is cut and why |
| [references.md](./references.md) | Numbered bibliography, cited `[R##]` |

## 6. Status

A **design target**. Implementation is separate work.

| Area | State |
|---|---|
| Learning engine, assistant runtime, direct delivery, messaging, auth | Brainstormed and locked |
| Hierarchy, content, account | Boundary locked; internals derived from the domain |
| Plans and credit | Shape locked; three values await measurement |
| Values to measure | Named with constraints, never invented |

Three preconditions are **not** design questions and block verification of
anything here: the gate is red, production cannot boot, and restore cannot run.
They are `P0.1`–`P0.3` at the top of [decisions.md](./decisions.md), and they are
fixed first.

## 7. Vocabulary

| Term | Meaning |
|---|---|
| **Sense** | One meaning of one word. The unit of learning and scheduling. |
| **Word** | A headword owning one or more senses. Lives in Lexi. |
| **Node** | One row in the tree: `FOLDER`, `DECK`, or `REFERENCE`. |
| **Deck** | A leaf node owning opaque Lexi `sense_id` membership. |
| **Reference** | A leaf node pointing live at another readable deck. The only cross-owner edge. |
| **Strength** | How long a sense is remembered. FSRS stability. Displayed as `mastery`. |
| **Depth** | How demanding a retrieval is: recognition through production. `depth_level` 0–4. |
| **Session** | One study activity over a planned set of senses. |
| **Round** | A bounded group of items followed by a break. UI pagination only. |
| **Thread** | One assistant conversation and its checkpoint namespace. |
| **Run** | One execution of the assistant graph on a Thread. |
| **Job** | One durable asynchronous unit of domain work. |
| **Credit** | The consumable that meters LLM work not shareable between learners. |
| **Lexi** | The embedded `lexi-ai` dictionary library. Owns schema `lexi`. |
