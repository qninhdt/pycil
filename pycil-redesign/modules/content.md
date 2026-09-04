# modules/content

Owns deck membership as opaque sense ids, dictionary reads, and question-supply
demand. Decisions `C1`–`C6`, `A5`.

Does not own the dictionary (the library does), grading (the library does), or node
authorization (`hierarchy` does).

## 1. The library boundary

Lexi is a **lazily-generating dictionary library**, not a layer of Pycil (`A5`). It
synthesises an entry on first lookup, anchors it against reference sources so it
cannot drift into invention, then caches — so every later lookup costs nothing.

| It owns | It must never own |
|---|---|
| words, senses, examples, collocations, forms, references, relations | a learner |
| tags, themes | learning progress or FSRS state |
| the question pool and its grading | the node tree |
| its own schema, its own migration chain | sessions, jobs, realtime |

The boundary is one rule: **Pycil stores a sense id as a plain integer with no
foreign key**, never joins across, never writes a dictionary table.

A leak is therefore not an import — it is either **Pycil knowing how the library is
implemented** or **the library knowing Pycil exists**.

Four properties keep it honest, and they are requirements rather than observations:

| Requirement | Why |
|---|---|
| The published contract **pins identity types** (`C4`) | Under-specification makes the consumer cast the same logical id between types at every boundary crossing, and wrap the cast in a handler — defending at runtime against its own dependency |
| The contract **carries its own render discriminator** (`C4`) | Naming the shape of a question is the library's knowledge. A consumer rebuilding it from a type ladder holds a second copy that drifts, and a new shape becomes a runtime failure instead of a type error |
| The contract publishes **`word_id_for(sense_id)`** (`C5`) | Without it a consumer needing the owning word constructs a whole presentation object to read one key |
| Retrieval and generation are **structurally separate** | See `C3` |

Keeping the wire name of a shape distinct from the library's internal type is
**deliberate**: it lets the library refactor a type without a wire break. So the
fix for a rebuilt discriminator is for the contract to *carry* it, not for the
consumer to adopt the internal name.

## 2. Two generation events, and only one is expensive

`C1`. Conflating them is what makes "AI generates the questions" sound like the
cost centre when it is not.

| | Generate a **word** | Generate **questions** |
|---|---|---|
| Trigger | a word not yet in the dictionary | a session needs supply at a level |
| Model calls | **one, synthesising the whole entry** — senses, definitions, examples, pronunciation, level, forms, relations | almost none |
| Frequency | **once per word, forever** | per round |
| Nature | synthesising new content | **assembling** from an entry that exists |
| Charged? | **no** — it enters the commons (`P11`) | **no** — same |

All content LLM spend is in the left column. Most question types are **mechanical
transforms** of the entry: a definition becomes a multiple-choice stem, an example
becomes a cloze, the inflected forms become accepted answers.

Exactly one type needs a model at preparation time — the level-2 contextual item,
because a plausible sentence with plausible distractors is not derivable from the
entry. And exactly one needs a model at **grading** time: the level-4 productive
item, which is the only thing in the product graded by a rubric rather than a
comparison.

That is the whole economic shape:

```text
word generation      one call per word ever          → free, shared
question supply      one type calls a model          → free, shared
L1-L3 grading        deterministic                   → free
L4 grading           a call per learner per answer   → CREDIT  (P5)
```

## 3. Supply is per word, shared by every learner

`C2`. The question pool is keyed by `(sense, level, type)` plus a content hash —
**not** by learner, not by session.

So the pool for a sense **grows and is reused**. The second learner to study a word
receives questions the first learner's session paid to generate, and question cost
per learner declines toward zero as the collection of learners grows.

This is why generation is not charged: charging for it would tax the contribution
the product depends on, and the payer would be whoever happened to arrive first.

Insertion is idempotent by content hash, checked **before and after** the write so
two concurrent producers converge on one row.

## 4. No retrieval path ever generates

`C3`, and it is the dividing line of the whole design.

```text
retrieve   exact: this sense, this level, this type, excluding what was already
           served. No fallback inside the library. Empty is an answer.

prepare    a durable job. Writes rows. Never on a request path.
```

Consequences:

- **the question read path never waits on a model call.** A learner pressing "next"
  waits on a database read, always;
- when supply is empty the client is **told** — preparing, waiting, or exhausted —
  not stalled behind a generation;
- supply is requested **ahead of need**: at session start for the first round, and
  on each round advance for the next.

Fallback is the *consumer's* decision, not the library's, and it has two
directions:

| Direction | Counts as a fallback? |
|---|---|
| A different **type** at the same level | **No** — normal resolution |
| A **lower level** | **Yes** — recorded, and it feeds the depth rule (`B7`) |

Changing type at one level is not a downgrade; only serving shallower is. Recording
which happened is what lets depth stay honest without punishing anyone.

## 5. Supply demand

The consumer asks for what a round still needs, keyed by `(sense, level)`. The job
is joined by a **work key of `(session, round)`** — not by the demand list — because
the demand is derived from what remains unresolved, so two calls within one round
compute *different* lists and keying on the list would generate one round's supply
twice (see [../cross-cutting/messaging.md](../cross-cutting/messaging.md) §8).

Two supply questions the design must answer explicitly, because the previous shape
answered them by accident:

**How many items per `(sense, level, type)`?** The demand carries a count, and the
count must be **honoured or removed from the contract**. A contract field the
producer ignores is worse than an absent one: the next reader takes it for a
promise. If honoured, each type needs a **variation source** — several examples for
a cloze, a wider distractor pool for a choice item — and the productive item has
none short of a model call.

**May a learner meet the same item again?** The exclusion set is **session-scoped**,
so a new session starts empty and previously served items recur. For spaced
repetition, re-recognition is still review — but it means an assessment can be
memorised rather than answered. This is a product decision with a real cost either
way: a durable exclusion set grows without bound, and a session-scoped one allows
memorisation. Recorded here as a decision the implementation must make deliberately,
not as a defect.

## 6. Deck membership

A deck holds **opaque sense ids** and nothing else. No cached definition, no cached
level, no copy of anything the library owns.

That is what makes the dictionary shareable: two learners with the same word in
their decks reference **one** sense row, and an improvement to that entry improves
both. A card-based product cannot do this — its cards are strings the learner
typed, so the same word in two accounts is two unrelated objects.

Reads join the learner's own state onto the dictionary view at the boundary:

| Listing a deck | One sense in detail |
|---|---|
| word, definition, level, part of speech | everything, plus pronunciation, register, collocations, usage notes, forms, relations |
| the caller's strength, depth, and next review | the same |
| one query for the whole deck | one query |

A listing stays lean **deliberately**: it is on a keystroke path when searching, so
each field added is paid for on every character typed by a UI that may not render
it. Full lexical detail belongs to the single-sense read.

Learning state is `None` for an anonymous viewer and for a sense never studied,
which the UI renders as "not started" rather than as zero — a distinction that
matters because zero strength is a real state a lapsed sense can be in.

## 7. Answer safety

`C6`. See [../cross-cutting/security.md](../cross-cutting/security.md) §4 for the
threat; here is the boundary rule.

The presentation type is **allowlisted per variant**: a field reaches the client
only because it is named in the allowlist for that shape. Not a blocklist of
answer-shaped names — a blocklist loses to a rename, and the failure is silent
because nothing breaks when an answer leaks. Assessment just stops meaning
anything.

An answer submission carries a **question identifier and an answer, never a
question payload**, so the server grades what it issued and there is nothing for a
client to tamper with.

The reveal is a separate payload issued **after** the answer is recorded.

## 8. Capabilities that may not be cut

Per R4:

- Pycil never writes a dictionary table and never joins across the boundary.
- No retrieval path generates.
- Supply is shared across learners and idempotent by content hash.
- The work key for supply is server-derived and never accepted from a client.
- The answer key never reaches the wire, enforced by a per-variant allowlist.
- A submission cannot carry its own question.
- Serving a lower level is recorded; changing type at one level is not.
- The library's contract pins identity types and names its own shapes.

## 9. Invariants for the checklist

```text
no Pycil query touches a dictionary table
retrieval never triggers generation
empty supply returns a state, not an error, and not a stalled request
a different type at the same level is not recorded as a fallback
a lower level is recorded as one
supply for one round is generated once under concurrent requests
the same question inserted twice yields one row
a client-supplied work key is rejected
an answer-shaped field never appears in any presentation schema
a submission carrying a question payload is ignored
a reveal is issued only after the answer is recorded
a deck listing carries no lexical detail beyond its declared fields
an unstudied sense reports no learning state, distinct from zero
a missing sense is a state, not a server error
```

## 10. Open, and it must be closed deliberately

Both from §5, both product decisions with a real cost either way:

1. **Is the per-demand item count honoured, or removed from the contract?**
   Honouring it needs a variation source per type. Removing it means the consumer
   must know that supply at a level equals the number of types at that level.
2. **May a learner meet the same item across sessions?** A durable exclusion set
   grows without bound; a session-scoped one allows an assessment to be memorised.
