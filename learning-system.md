# Learning System Design

## Overview

This document defines Pycil's vocabulary-learning session, question-type,
difficulty, retry, and FSRS policies.

The system optimizes, in order, for:

1. Long-term retention.
2. Question diversity.
3. Response time.

Users configure how many unique words they want to study and the maximum number
of items shown before a round break. The number of questions is derived from the
selected words, acquisition checkpoints, and retries; it is not a fixed session
contract.

## Core Principles

- A sense, not a word spelling, is the unit of learning and scheduling.
- Initial acquisition and scheduled retention are separate phases.
- A new sense is shown before it is tested.
- Same-session retries teach and repair; they do not create repeated FSRS
  updates.
- A scheduled review is graded once per session: `Good` only when every one of
  its N checkpoints is first-attempt correct, otherwise `Again`.
- Question difficulty is a shared pedagogical scale across every question type.
- Each question type is a self-contained plugin owning its own generation,
  retrieval, and grading behind one technology-neutral interface.
- Diversity is stochastic and does not require persisted type or level history.
- Session work is bounded. Only FSRS state is durable; unfinished acquisition
  and retries are dropped at session end rather than carried.

## Terminology

| Term | Meaning |
|---|---|
| Sense | The canonical semantic unit being learned and scheduled. |
| Session | A study activity containing a configured number of unique senses. |
| Round | A bounded group of items followed by a user break. A sense appears at most once per round. |
| Exposure | A level-0 flashcard presentation with no answer or grade. |
| Checkpoint | One of the N items a sense must complete in a session. Completed by answering correctly; a wrong answer is retried. |
| Acquisition | The initial process of completing the exposure plus N level-1 checkpoints for a new sense. |
| Scheduled sense | A sense that has completed acquisition and has an FSRS memory state. |
| Due | A derived time condition: the sense's next scheduled review time has arrived. |
| Requested level | The difficulty the planner selected for a checkpoint. |
| Served level | The difficulty of the item actually returned by the resolver. |
| Disqualifying event | A wrong first attempt or a served level below the requested level. It locks the session grade to `Again`. |
| Fallback | An item served below the requested level. It still advances state, but it is a disqualifying event for the score. |
| State | Completion progress: how many of the N checkpoints are done. |
| Score | The single FSRS grade a sense earns in a session: `Good` only if clean, else `Again`. |

## Word Lifecycle

Every sense follows this lifecycle:

```text
new -> acquiring -> scheduled
```

### New

The user has not encountered the sense in the learning system. It has no FSRS
state and no mastery value.

### Acquiring

The user has seen the level-0 flashcard but has not completed all required
level-1 checkpoints. `acquiring` is a session-local phase, not a durable
lifecycle state. If a session ends before acquisition completes, the sense
remains `new`; a later session restarts acquisition from exposure. Nothing
except FSRS state is durable.

### Scheduled

The sense has completed acquisition in a single session and owns an FSRS memory
state. It becomes due according to `next_review_at`, independently of its
displayed mastery.

There is no persistent `mastered` lifecycle state. High mastery means high
memory stability, not permanent completion.

## Mastery, Due State, and Difficulty

These concepts are independent:

| Concept | Question answered |
|---|---|
| Lifecycle phase | Has the sense entered FSRS scheduling? |
| Due state | Is it time to review the sense now? |
| Mastery | How stable is the memory? |
| Difficulty level | How demanding is this learning item? |
| Session purpose | Is this exposure, acquisition, scheduled review, or remediation? |

Pycil derives displayed mastery from FSRS stability:

```text
mastery = round(100 * stability / (stability + 30))
```

Due state is derived from time:

```text
due = now >= next_review_at
```

A high-mastery sense eventually becomes due. A low-mastery sense is not due
before its scheduled time.

## Difficulty Scale

Pycil uses five pedagogical stages: level 0 is ungraded exposure, and levels
1-4 are graded difficulty levels. The scale measures retrieval demand and
response freedom, not sentence length or superficial complexity.

```text
0 = Exposure
1 = Direct recognition
2 = Contextual discrimination
3 = Cued recall
4 = Productive use
```

### Level 0: Exposure

Level 0 is always a flashcard and never an assessment question.

It may present:

- Word form.
- Pronunciation or audio.
- Part of speech.
- Definition.
- Example usage.
- Translation when supported by the product.

Level 0 has no answer, correctness, grade, acquisition credit, or FSRS update.

### Level 1: Direct Recognition

The target word is visible, the correct meaning or sense is present among the
candidates, and context is not required to identify the answer.

Examples include:

- Definition multiple choice.
- Word-to-definition matching.
- Word-to-image matching.
- Direct meaning verification.

Example:

```text
"scarce" means:

- plentiful
- limited
- noisy
- ancient
```

### Level 2: Contextual Discrimination

The answer remains visible among candidates, but the learner must use context,
reverse mapping, or semantic discrimination to select it.

Requirements:

- The answer is visible.
- Direct word-to-definition lookup is insufficient.
- Context or direction reversal matters.
- Alternatives are plausible for the prompt.

Examples include:

- Contextual multiple choice.
- Reverse definition multiple choice.
- Cloze with a word bank.
- Sense disambiguation.

Example:

```text
Food became ______ after the supply routes were blocked.

- vivid
- scarce
- reluctant
- concise
```

### Level 3: Cued Recall

The answer is not shown. The learner must retrieve it, but the prompt strongly
constrains the response space.

Requirements:

- No answer candidates are visible.
- A clear cue or context is present.
- One answer or a small group of answers is acceptable.
- The learner does not need to construct the entire context.

Examples include:

- Typed cloze.
- Typed definition or translation.
- Cued collocation recall.
- Completing a constrained phrase without options.

### Level 4: Productive Use

The answer is not shown and the response space is open. The learner must use
the target sense appropriately in a new context.

Requirements:

- No answer candidates are visible.
- Multiple surface responses may be valid.
- The target sense must be semantically appropriate.
- Basic grammatical and collocational fit may be required.
- General writing quality outside the target sense is not part of the grade.

Examples include:

- Use the target word in a sentence.
- Rewrite a statement using the target word.
- Respond to a situation with the target vocabulary.
- Open contextual production.

### Level Assignment Decision Tree

```text
Is the item presentation-only?
  yes -> level 0
  no  -> continue

Is the answer visible among candidates?
  yes -> direct form/meaning recognition? level 1
         context, reverse mapping, or discrimination required? level 2
  no  -> response tightly constrained by a cue? level 3
         open productive response? level 4
```

Longer prompts, rarer words, harder distractors, and more complex grammar do not
alone move an item to a higher level. A difficult multiple-choice item remains
level 1 or 2 because the answer is visible. A simple typed recall item remains
level 3 because the answer must be retrieved.

### Expected Type Coverage

The type registry may initially contain coverage similar to:

| Type (`format_id`) | Supported levels |
|---|---|
| Flashcard | `{0}` |
| Definition multiple choice | `{1, 2}` |
| Contextual multiple choice | `{1, 2}` |
| Cloze | `{2, 3}` |
| Use in sentence | `{3, 4}` |

Each type declares an explicit set of supported levels. A contiguous range is
common but not required.

## Score and State Are Separate

The system tracks two independent things about a sense within a session:

- **State** is progress: how many of the sense's `N` checkpoints are done. State
  is driven by completion, not by correctness. A checkpoint is done once it is
  answered correctly; a wrong answer is retried in a later round until it is
  correct or the retry limit is hit.
- **Score** is the single FSRS grade the sense earns. Score depends on *how*
  the checkpoints were completed: clean versus blemished.

Confusing the two is the mistake this section prevents. Finishing the work and
earning a `Good` are different events.

### State: Completion

A sense is *complete* in a session when all `N` checkpoints are answered
correctly. Retrying a wrong checkpoint is redoing that checkpoint, not a new
one. A checkpoint may be satisfied by a question served at the requested level
or, when that level is unavailable, by a fallback at a lower level.

A sense stops being worked when it completes all `N` checkpoints, when a
checkpoint exhausts `MAX_RETRIES_PER_CHECKPOINT`, or when the session ends.

### Score: the FSRS Grade

A sense earns at most one FSRS grade per session:

```text
every checkpoint first-attempt correct at its requested level -> Good
any wrong first attempt, or any fallback below requested level -> Again
```

A *disqualifying event* is a wrong first attempt or a served level below the
requested level. The first disqualifying event locks the grade to `Again` and
applies it immediately: it is authoritative evidence the memory has decayed or
was never demonstrated at the intended level. `Good` is applied only when the
sense completes all `N` checkpoints with no disqualifying event.

If the session ends with neither outcome reached (no disqualifier yet, but not
all `N` done), no FSRS grade is applied; the sense re-enters as a due review
later. This gives at most one FSRS update per sense per session, changing
stability, difficulty, displayed mastery, review history, and `next_review_at`.

Fallback still delivers a real, answerable question and still advances state:
the learner keeps moving and the sense never gets stuck waiting for an
unavailable level. What fallback costs is the `Good`, not the progress.

## New-Sense Acquisition

The global backend setting is:

```text
REQUIRED_CHECKPOINTS = N
```

`N` is the number of checkpoints a sense must complete in a single session. It
is shared by acquisition and scheduled review. It is a backend policy value, not
a user or deck setting.

Acquisition proceeds as follows:

1. First encounter: serve a level-0 flashcard (exposure only, never graded).
2. Later rounds: request `N` level-1 checkpoints, each in a separate round.
3. When all `N` checkpoints are complete, move the sense to `scheduled` with its
   initial FSRS grade.

Level 0 does not count toward the `N` checkpoints. Every acquisition checkpoint
requests level 1; acquisition does not sample a difficulty, because a new sense
has no mastery to sample from. Level 1 is the assessment floor, so acquisition
checkpoints do not fall back; the only disqualifying event is a wrong first
attempt.

A wrong checkpoint is retried with a different level-1 question in a later
round, bounded by `MAX_RETRIES_PER_CHECKPOINT`. Completing acquisition after a
stumble is still completion: the learner does not restart from exposure. The
stumble only affects the score.

The initial FSRS grade follows the same rule as any review:

```text
all N checkpoints first-attempt correct -> initial Good
any wrong first attempt                 -> initial Again
```

A new sense has no FSRS state until it completes acquisition, so an incomplete
acquisition writes nothing. If a checkpoint exhausts its retries or the session
ends first, the sense stays `new` and a later session starts over from exposure.

Completing acquisition means the sense is ready for spaced review, not that it is
mastered. With the current FSRS defaults, an initial `Good` produces low mastery
and a near-term first scheduled review; an initial `Again` schedules it even
sooner.

## Scheduled Reviews

A due scheduled sense is reviewed with `N` checkpoints, exactly like acquisition
except each checkpoint samples its requested level independently from the sense's
mastery profile instead of being fixed at level 1. It follows the same
score-and-state rules:

- State: complete all `N` checkpoints, retrying wrong ones (bounded).
- Score: `Good` only if every checkpoint is first-attempt correct at its
  requested level; `Again` on the first wrong attempt or first fallback.

After a disqualifying event, the learner still finishes the remaining
checkpoints as session-local repair. Those later checkpoints never add a second
FSRS update. Feedback is shown after every attempt.

Nothing carries over. If the session ends before completion, the sense keeps
whatever single FSRS grade the session already applied (`Good`, `Again`, or none)
and re-enters naturally as a due review later.

## Question Type Architecture

A **question type** is a self-contained plugin. Each type owns everything about
one kind of question: how it prepares supply, how it produces a question, and
how it grades an answer. Adding a new kind of question means adding one new type
and registering it. The engine never branches on a specific kind.

A type is identified by `format_id`. That single identity serves three roles:

- It is the type's registry key.
- It is the UI's render contract (radio choices, cloze blank, typed input,
  productive text), which already implies the shape of the answer the client
  sends. There is no separate `answer_kind`.
- It labels the question for analytics.

The engine routes only on `supported_levels` (to fetch) and `format_id` (to
grade the question it delivered). It never inspects a type's internals.

### Type Descriptor

```text
QuestionTypeDescriptor:
  format_id
  supported_levels: set[int]
```

### Preparation Demand

```text
QuestionDemand:
  sense_id
  difficulty_level
  expected_count
```

### Exact Query

```text
QuestionQuery:
  sense_id
  difficulty_level
  excluded_question_ids: set[QuestionId]
```

### Question

```text
Question:
  question_id
  sense_id
  format_id            # type identity + UI render contract + answer shape
  difficulty_level
  interaction_mode: exposure | assessment
  payload              # self-contained context (rubric, target sense) for grading
```

Level 0 uses `interaction_mode = exposure` and has no gradable answer. Levels
1-4 use `interaction_mode = assessment`.

### Question Type Interface

```text
QuestionType:
  descriptor -> QuestionTypeDescriptor
  prepare(demands: Sequence[QuestionDemand]) -> None
  retrieve(query: QuestionQuery) -> Question | None
  evaluate(question: Question, answer: Answer) -> Evaluation
```

`prepare` is a session-planning lifecycle hook. A type receives the demands
relevant to its supported levels and decides how to satisfy them. The learning
domain does not inspect or control that decision.

`retrieve` requests one exact difficulty from one type. It returns a matching
question immediately or `None`. It does not return a lower-level question; level
fallback belongs to the resolver.

`evaluate` grades an answer to a question the same type produced. It is covered
in Answer Evaluation below.

The Python implementation may use `async` methods for I/O, but `prepare` and
`retrieve` remain direct request/response operations.

### Registration

```text
register(question_type):
  type_registry.add(question_type.format_id, question_type)
```

Adding a question kind touches only: one new `QuestionType`, one `register`
call, and the UI's ability to render the new `format_id`. It does not touch the
engine, resolver, level fallback, round scheduler, FSRS logic, session
lifecycle, or the score and state rules.

## Question Resolver

### Resolver Request

```text
QuestionResolutionRequest:
  sense_id
  requested_level
  excluded_question_ids
```

There is no preferred format. The engine routes on level and shuffles the
eligible types; the delivered question's `format_id` is whatever the chosen
type stamps on it.

### Resolver Result

```text
ResolvedQuestion:
  question
  requested_level
  served_level
  is_fallback
```

The served `format_id` is read from `question.format_id` for the UI. It is not a
routing input.

### Resolution Algorithm

For an assessed question, the resolver searches from the requested level down
to level 1. The engine, not any type, shuffles the eligible types:

```text
for level from requested_level down to 1:
    types = types supporting level
    engine shuffles those types uniformly

    for question_type in shuffled order:
        question = question_type.retrieve(sense_id, level, excluded ids)
        if question exists:
            return it with requested_level, served_level = level

return None
```

The effective fallback order is:

```text
all types at level K   (uniform random order)
all types at level K-1 (uniform random order)
...
all types at level 1
None
```

A final `None` means no type can supply any eligible item. The session
scheduler defers the requirement and selects another sense; it does not expose
an empty question to the learner.

Level-0 exposure is resolved directly through a type supporting level 0 and
does not enter the assessed fallback loop.

## Answer Evaluation

Grading is dispatched per question through the type that produced it:

```text
grade(question, answer):
    question_type = type_registry.get(question.format_id)
    return question_type.evaluate(question, answer)
```

The engine stays blind to how any kind is graded. Two questions sharing a
render shape may still grade differently, because each belongs to its own type
and each type owns its `evaluate`.

### Evaluation Is a State Machine

Grading is not assumed to be instantaneous. `evaluate` returns an `Evaluation`
whose status may settle later:

```text
Evaluation:
  status: pending | graded
  verdict: correct | incorrect   # present only when graded
  stream_channel                 # optional; partial updates before settling
```

- Exact-match kinds (single choice, exact text, rule-based cloze) return
  `graded` immediately.
- Model-graded kinds (productive use, open recall) return `pending`, then settle
  through the existing lease and poll grading path.
- A future streaming grader still returns `pending` and pushes partial updates
  on `stream_channel`; the final settle is a single `graded` verdict. The engine
  handles all three identically.

`evaluate` reads everything it needs from `question.payload` (rubric, target
sense). It does not query the lexicon itself, so every type stays
self-contained.

### Grading and the Round Flow

The round never blocks on grading:

- A submitted checkpoint whose evaluation is `pending` enters `awaiting_grade`.
- The learner proceeds to the next item (a different sense) while it settles.
- The checkpoint's pass, retry, and FSRS consequences are deferred until the
  grade settles.
- Because sessions sync across devices, a settled grade is pushed over the
  existing realtime channel.

A session is not complete while any checkpoint is still `awaiting_grade`. The
session ends only when every admitted sense is terminal and no grade is pending,
or when the learner explicitly exits.

## Difficulty Selection After Acquisition

Difficulty selection is non-uniform. Mastery selects a backend-configured
probability profile rather than one fixed level.

Initial global profiles:

| Mastery | Level 1 | Level 2 | Level 3 | Level 4 |
|---:|---:|---:|---:|---:|
| 0-10 | 90% | 10% | 0% | 0% |
| 11-30 | 65% | 30% | 5% | 0% |
| 31-55 | 20% | 55% | 23% | 2% |
| 56-80 | 5% | 25% | 55% | 15% |
| 81-100 | 0% | 10% | 50% | 40% |

These profiles are configurable backend defaults, not fixed policy. They provide
a dominant challenge band plus lower-probability adjacent levels, avoid a
one-to-one mastery-to-level mapping, and prevent abrupt transitions where every
question changes difficulty at one threshold.

The planner samples the requested level from the applicable profile. It does not
choose a type: the engine passes only `(sense_id, requested_level)` to the
resolver, which uniformly shuffles the types supporting that level. The
`format_id` of the returned question is whatever the winning type stamped on it,
used only for UI rendering and analytics.

Diversity is stochastic over repeated study and is not forced through persisted
recent-type, recent-level, or coverage counters.

The session keeps only `excluded_question_ids` so the same concrete question is
not served twice in one session. This is especially important for acquisition
and remediation, where remembering the prior prompt must not count as retrieval
of the sense.

## Session Planning

### User-Facing Settings

```text
target_words_per_session
max_questions_per_round
```

`target_words_per_session` is the number of unique senses admitted to the
session. It replaces a fixed total-question setting.

`max_questions_per_round` defines the attention and break boundary. A round may
contain fewer questions but never more.

### Backend Safety Settings

```text
REQUIRED_CHECKPOINTS = 2
MAX_RETRIES_PER_CHECKPOINT = 2
NEW_WORD_FLOOR = 2
```

`REQUIRED_CHECKPOINTS` (`N`) is the number of checkpoints a sense needs to
complete in one session. It applies to both acquisition (`N` level-1 checkpoints)
and scheduled review (`N` checkpoints, each at a level sampled from the mastery
profile).

`MAX_RETRIES_PER_CHECKPOINT` bounds how many times one failed checkpoint is
retried before the session gives up on that sense and drops the unfinished work.

`NEW_WORD_FLOOR` reserves a minimum number of session slots for new senses even
when the due backlog is large, so learners never get an all-review session while
new material exists.

All three are global backend policy values, not user or deck settings.

There is no total-question ceiling. A session ends when every admitted sense
reaches a terminal state and no grade is pending, or when the learner explicitly
exits. Per-checkpoint retries are still bounded by `MAX_RETRIES_PER_CHECKPOINT`,
so a single sense cannot loop forever, but the session length itself is governed
by the admitted senses reaching terminal states, not by a fixed question cap.

### Candidate Selection

`target_words_per_session` is the total number of unique senses admitted,
counting due reviews, new senses, and any that pass through acquisition in the
session. It measures admitted work, not guaranteed completion: because nothing
carries over, a session may admit the full target yet finish only some senses.

Retention is the top priority, so due reviews fill the session first. A new-word
floor keeps every session from becoming pure review while new material remains:

```text
new_slots = max(NEW_WORD_FLOOR, target_words_per_session - due_available)
due_slots = target_words_per_session - new_slots
```

The planner then builds the target set:

1. Admit up to `due_slots` scheduled senses that are due, ordered by lowest
   retrievability and greatest overdue pressure.
2. Admit up to `new_slots` new senses.
3. If either source is short, the other fills the remaining slots up to
   `target_words_per_session`.

There is no carried acquisition or remediation source: acquisition is completed
within a single session or not at all, and remediation is session-local. Buried
senses are excluded. A sense appears only once in the admitted target set.
Scheduled senses that are not due are not selected by default.

### Base Plan

For each admitted sense, the planner creates requirements rather than locking all
question identifiers:

- New sense: level-0 exposure plus `N` future level-1 checkpoints.
- Due scheduled sense: `N` checkpoints, each with a requested level independently
  sampled from the sense's mastery profile. The engine, not the plan, selects a
  question type at delivery time.

The plan estimates expected demand per sense and level, then invokes `prepare`
on registered question types with the relevant demands.

Retry requirements are added dynamically after incorrect checkpoints. They
preserve the original requested level and exclude previously served question
identifiers.

## Round Scheduling

A round is a variable-size wave with a maximum question count.

Rules:

- A sense appears at most once in a round.
- The scheduler does not introduce every session word in the first round.
- Acquisition checkpoints and retries occur in later rounds, never immediately
  after the originating item.
- A retry waits at least one round, creating intervening practice.
- Requirements that cannot be resolved are deferred while other senses continue.
- A break is offered after every round.

When more eligible items exist than a round can hold, the scheduler fills the
round in this priority order. It closes open work before opening new work:

```text
1. Eligible retries        (failed checkpoint, waited >= 1 round)
2. Due-review checkpoints  (retention)
3. Acquisition checkpoints (level 1, for an already-exposed sense)
4. New exposures           (level 0)
```

There is no separate anti-starvation rule. Each sense needs a fixed `N`
checkpoints, the session is bounded, and unfinished work is dropped at session
end rather than protected.

Example for `target_words_per_session = 12` and
`max_questions_per_round = 5`:

```text
Round 1: 5 items -- initial exposures and due reviews
Break
Round 2: 5 items -- more senses plus acquisition checkpoints
Break
Round 3: 5 items -- checkpoints, reviews, and remediation
Break
Round 4: remaining bounded work
```

The number of rounds and questions is dynamic because incorrect answers create
remediation work. The session is still bounded: each sense needs a fixed `N`
checkpoints, each checkpoint is retried at most `MAX_RETRIES_PER_CHECKPOINT`
times, and the session ends when every admitted sense is terminal or the learner
exits.

## Attempt and State-Update Rules

Every delivered assessment creates an attempt record. Each attempt affects two
independent things: **state** (checkpoint completion) and **score** (the sense's
one FSRS grade). A *disqualifying event* is a wrong first attempt or a served
level below the requested level.

| Attempt | State effect | Score effect |
|---|---|---|
| First attempt, correct, at requested level | Complete the checkpoint | Keep `Good` eligibility |
| First attempt, wrong, at requested level | Checkpoint stays open; retry later | First disqualifier -> lock `Again` and apply it now |
| Fallback, served below requested level | Complete the checkpoint | First disqualifier -> lock `Again` and apply it now |
| Retry after a wrong checkpoint | Complete the checkpoint when correct | None; the grade was already decided |
| Level-0 exposure | Mark exposure delivered | None |

Grade timing:

- `Again` is applied immediately on the first disqualifying event.
- `Good` is applied once, when all `N` checkpoints complete with no disqualifier.
- If the session ends before either outcome, no grade is applied.

A sense receives at most one FSRS update per session. For a new sense the same
rule produces its initial grade at acquisition completion. The durable
idempotency key on the FSRS write guards against duplicate updates from
concurrent or retried submissions, even if session-scoped state is lost.

## Session Completion and Carryover

A session admits the configured number of unique senses, but individual learning
requirements may remain unresolved when safety limits are reached.

At session end, each admitted sense is summarized as one of:

- Acquisition completed clean (moved to `scheduled` with initial `Good`).
- Acquisition completed after a stumble (moved to `scheduled` with initial
  `Again`).
- Scheduled review completed clean (`Good`).
- Scheduled review completed with a disqualifier (`Again`, then repaired).
- Incomplete (no grade applied yet; stays `new`, or keeps its prior `scheduled`
  state).

Completion is state; the grade is score. A stumbled-but-completed sense still
counts as completed. Nothing except FSRS state is durable: incomplete
acquisition and unfinished checkpoints or retries are dropped, and the sense
re-enters naturally in a later session. A session never loops indefinitely to
force a correct answer.

## Preparation and Resolution Failure Semantics

Preparation and resolution failures never produce an empty or malformed
question. They are nevertheless observable when the bounded recovery budget is
exhausted; they are not all silently ignored or converted into clean session
completion.

### `prepare` errors or latency

`prepare` is asynchronous supply warm-up, not a delivery guarantee:

- Session creation makes a best-effort enqueue attempt. Enqueue failure does not
  invalidate the newly created session; the consumed attempt enters cooldown.
- `/next` always runs exact retrieval and resolver fallback before consulting the
  preparation retry gate, so late-arriving supply remains deliverable.
- If unresolved demand remains, `/next` claims a session-scoped preparation
  attempt. Claimed or cooldown-waiting attempts return `preparing`; enqueue
  failures are retried on a later eligible poll.
- Preparation is bounded to three attempts per session with a ten-second
  cooldown, in addition to the owner generation quota. Once that budget is
  exhausted, `/next` raises `question_preparation_exhausted`.

### Resolver `None` for one sense

When the resolver returns `None` for one requirement, the scheduler defers that
sense and tries other eligible work in the round. The learner is never shown an
empty question.

### Resolver `None` for every eligible sense

When every eligible assessed requirement is unresolved, the session enters the
bounded preparation flow above. It returns `preparing` while an attempt can be
claimed or is cooling down. If exact retrieval still cannot supply an item after
the final attempt, the API returns `question_preparation_exhausted`; it does not
claim that the session completed cleanly.

A clean `exhausted` state is reserved for sessions whose admitted work is
actually terminal and has no pending grade. Requirements stopped by checkpoint
retry exhaustion are terminal unfinished work; explicit learner exit still
discards remaining session-local state.

## Persistence Contract

State is split into two tiers. Only the durable tier survives a session.

### Durable (Postgres)

Survives across sessions:

- FSRS memory state per sense: `stability`, `difficulty`, `last_review_at`,
  `next_review_at`, `review_count`.
- FSRS review log: one row per FSRS update, recording the grade (`Good` or
  `Again`) and its timestamp. A failed checkpoint's `Again` is logged as its own
  observation, so the log reflects every FSRS-affecting event.
- Lifecycle: `new` or `scheduled`. `acquiring` is never persisted.

### Session-scoped (Redis)

Discarded when the session ends:

- Admitted sense set with each sense's purpose (`due` or `new`).
- Per-sense checkpoint progress: passed count out of `N`, and whether an FSRS
  update has already been applied this session.
- `excluded_question_ids`.
- Retry state: which checkpoint is open and its `retries_used`.
- Round index and per-round item count.
- The durable first-attempt claim that guards against double grading.

Because acquisition progress and all checkpoint state live only in Redis, a
session that ends early loses everything except the durable FSRS tier, exactly
as the no-carryover rule requires.

## Question Type and Session Invariants

1. Every question type declares exactly which difficulty levels it supports.
2. `retrieve` either returns the exact queried level or `None`; types never
   perform cross-level fallback.
3. Only the resolver performs level fallback, and only the engine shuffles the
   eligible types; `format_id` is never a routing input.
4. Grading is dispatched by `question.format_id` to the type that produced the
   question; the engine never branches on a specific kind.
5. The same question identifier is not served twice in one session.
6. A sense is not served twice in one round.
7. Level 0 is always exposure-only and never graded.
8. New senses always receive level 0 before any checkpoint.
9. New-sense checkpoints always request level 1 and never fall back.
10. State and score are separate: completion counts `N` correctly-answered
    checkpoints regardless of stumbles; the grade depends on how they were
    completed.
11. A sense earns `Good` only when every checkpoint is first-attempt correct at
    its requested level; a wrong first attempt or any lower-level fallback locks
    the grade to `Again`.
12. Fallback still advances state and is answerable; it only forfeits `Good`.
13. A sense receives at most one FSRS update per session, applied on the first
    disqualifier (`Again`) or on clean completion (`Good`).
14. Repair checkpoints after a disqualifier never add a further FSRS update.
15. Nothing except FSRS state is durable across sessions; `acquiring` is never
    persisted.
16. Session work is bounded by `N` and `MAX_RETRIES_PER_CHECKPOINT`; a session
    ends when every admitted sense is terminal with no grade pending, or when
    the learner exits.

## Integration Boundaries

The design interacts with these existing Pycil responsibilities:

- Session creation and scope validation.
- Sense candidate selection and buried-sense filtering.
- Redis session and round state.
- Durable answer claims and response records.
- FSRS state, mastery projection, and review logs.
- Embedded lexical content and question capabilities.
- Question-type registration and resolution.

The learning domain owns:

- Session and round policy.
- Requested difficulty selection.
- Question-type ordering and level fallback.
- Score-and-state decisions.
- Acquisition, review, and remediation transitions.
- FSRS update eligibility.

Each question type owns:

- Its `format_id` and UI render contract.
- Its supported difficulty levels.
- Its preparation behavior.
- Returning an exact-level question or `None`.
- Grading its own answers via `evaluate`.

## Observability and Success Metrics

### Learning Outcomes

- First-attempt correctness at the next due review.
- Failure rate at the first scheduled review after acquisition.
- First-attempt correctness by difficulty level and format.
- Same-session remediation success followed by next-review retention.
- Acquisition attempts required per sense.
- Rate of senses left unfinished at session end (dropped, not carried).

### Session Experience

- Sessions completed and abandoned.
- Questions and rounds per session.
- Unique senses per completed session.
- Extra questions caused by retries.
- Time per round and break continuation rate.
- Frequency with which a single sense reaches its retry limit.

### Question-Type and Resolver Health

- `prepare` duration by question type.
- `retrieve` duration and `None` rate by question type and level.
- `evaluate` latency and pending-settle time by question type.
- Same-level alternate-type resolution rate.
- Lower-level fallback rate and depth.
- Final resolver `None` rate.
- Duplicate-question rate within a session, which should be zero.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Incorrect answers make sessions unexpectedly long | Per-checkpoint retry limits and dropping unfinished work at session end |
| A question type cannot supply the requested level | Session-time preparation, same-level alternate types, lower-level fallback that still advances state, defer unresolved requirement |
| Lower-level fallback inflates mastery | A fallback below the requested level locks the session grade to `Again`, so an easier item never earns `Good` |
| Learner memorizes a prompt instead of the sense | Exclude all question identifiers already used in the session |
| New words are treated as durable memories after one easy answer | Level-0 exposure plus N level-1 checkpoints in separate rounds before FSRS |
| Question difficulty changes abruptly with mastery | Non-uniform multi-level probability profiles |
| One question type dominates through fixed routing | Engine uniformly shuffles eligible types at the selected level |
| Production grading becomes a general writing assessment | Level-4 grading is limited to target-sense appropriateness and necessary grammatical or collocational fit |

## Acceptance Criteria

The design is correctly implemented when:

1. A new sense is first delivered as an ungraded level-0 flashcard.
2. A new sense enters FSRS only after `N` passed level-1 checkpoints in separate
   later rounds.
3. A failed acquisition checkpoint is retried with a different level-1 question
   in a later round and does not erase already passed checkpoints.
4. A due scheduled sense receives exactly one FSRS update per session: `Good`
   only when all `N` checkpoints are first-attempt correct, otherwise `Again` on
   the first incorrect checkpoint.
5. After a scheduled sense fails a checkpoint, its remaining checkpoints are
   completed as session-local repair without any second FSRS update.
6. A question served below the requested level still advances checkpoint state,
   but locks the session's FSRS grade to `Again`; it never earns `Good`.
7. A question type exposes only descriptor, preparation, retrieval, and
   evaluation behavior; its internals do not leak into learning policy.
8. Resolver fallback tries all eligible types at the current level, shuffled
   by the engine, before moving to the next lower level; `format_id` is never a
   routing input.
9. Difficulty after acquisition is sampled from a non-uniform mastery profile,
   not mapped to one fixed level.
10. Question-type and format diversity is stochastic and requires no persisted
    coverage history.
11. A sense appears at most once per round, and a round never exceeds its
    configured question maximum.
12. Session length remains bounded even when learners repeatedly answer
    incorrectly.

## Research Basis

- Laufer and Goldstein describe and validate a four-part vocabulary-strength
  hierarchy: passive recognition, active recognition, passive recall, and active
  recall. This supports four graded retrieval stages rather than a more finely
  divided scalar: <https://doi.org/10.1111/j.0023-8333.2004.00260.x>.
- Vocabulary Knowledge Scale research shows why exposure, recognition, recall,
  and production require explicit operational boundaries when used in one
  progression: <https://www.researchgate.net/publication/230809064_Comparing_Multidimensional_and_Continuum_Models_of_Vocabulary_Acquisition_An_Empirical_Examination_of_the_Vocabulary_Knowledge_Scale>.
- Multiple-choice tasks can induce retrieval when alternatives are competitive,
  but answer visibility still distinguishes them from cued recall:
  <https://pubmed.ncbi.nlm.nih.gov/25123774/> and
  <https://pubmed.ncbi.nlm.nih.gov/30113206/>.
- The CEFR Companion Volume separates receptive and productive language activity
  and distinguishes vocabulary range from vocabulary control, supporting the
  constraint that productive vocabulary questions grade the target sense rather
  than general writing proficiency:
  <https://rm.coe.int/cefr-companion-volume-with-new-descriptors-2020/16809ea0d4>.
- Retrieval practice and spacing support delayed retention, while repeated
  same-day practice should remain a bounded acquisition or remediation activity:
  <https://learninglab.psych.purdue.edu/downloads/2010/2010_Karpicke_Roediger_MC.pdf>.

## Next Step

Create an implementation plan that maps this specification onto the existing
session store, learning router, FSRS service, question-type registry, schemas,
persistence, and test suites. No implementation should begin before that plan is
reviewed.
