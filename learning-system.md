# Learning System Design

## Overview

This document defines Pycil's vocabulary-learning session, question-provider,
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
- The first qualifying attempt of a scheduled review is the authoritative FSRS
  observation.
- Question difficulty is a shared pedagogical scale across every format.
- Question providers are black boxes behind one technology-neutral interface.
- Diversity is stochastic and does not require persisted format or level history.
- Session work is bounded. Unresolved work carries into a later session rather
  than creating an infinite loop.

## Terminology

| Term | Meaning |
|---|---|
| Sense | The canonical semantic unit being learned and scheduled. |
| Session | A study activity containing a configured number of unique senses. |
| Round | A bounded group of items followed by a user break. A sense appears at most once per round. |
| Exposure | A level-0 flashcard presentation with no answer or grade. |
| Acquisition | The initial process of completing the required level-1 checkpoints for a new sense. |
| Scheduled sense | A sense that has completed acquisition and has an FSRS memory state. |
| Due | A derived time condition: the sense's next scheduled review time has arrived. |
| Requested level | The difficulty selected by the session planner for an item. |
| Served level | The difficulty of the item actually returned by the resolver. |
| Qualifying attempt | An attempt whose served level equals its requested level. |
| Fallback practice | An attempt served below the requested level. It is recorded but does not affect acquisition or FSRS. |
| Remediation | A later-round attempt after an incorrect qualifying attempt. |

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
level-1 checkpoints. Acquisition progress persists across sessions.

### Scheduled

The sense has completed acquisition and owns an FSRS memory state. It becomes
due according to `next_review_at`, independently of its displayed mastery.

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

### Expected Provider Coverage

The provider registry may initially contain coverage similar to:

| Format | Supported levels |
|---|---|
| Flashcard | `{0}` |
| Definition multiple choice | `{1, 2}` |
| Contextual multiple choice | `{1, 2}` |
| Cloze | `{2, 3}` |
| Use in sentence | `{3, 4}` |

Providers declare an explicit set of supported levels. A contiguous range is
common but not required.

## New-Sense Acquisition

The global backend setting is:

```text
NEW_WORD_REQUIRED_CHECKPOINTS = 2
```

It is not a user or deck setting.

Acquisition proceeds as follows:

1. First encounter: serve a level-0 flashcard.
2. Later round: request a level-1 checkpoint.
3. Later round: request a second level-1 checkpoint.
4. After both checkpoints pass, create the initial FSRS `Good` observation and
   move the sense to `scheduled`.

Level 0 does not count toward the two checkpoints. Every acquisition checkpoint
requests level 1; acquisition does not randomly select a difficulty.

A checkpoint passes only when:

- The served item is level 1, equal to the requested level.
- The first attempt on that item is correct.
- The item has not previously appeared in the session.

An incorrect checkpoint remains open. Feedback is shown, and a different
level-1 question is requested in a later round. Previously completed checkpoints
remain completed. Acquisition stops retrying when a backend safety limit is
reached; unresolved progress carries to a later session.

Completing acquisition means the sense is ready for spaced review. It does not
mean the sense is mastered. With the current FSRS defaults, the initial `Good`
produces low mastery and a near-term first scheduled review.

## Scheduled Reviews and Remediation

### Authoritative Review Attempt

For a due scheduled sense, the first qualifying attempt is the only attempt that
updates FSRS in that session:

```text
correct -> FSRS Good
incorrect -> FSRS Again
```

The update changes stability, difficulty, displayed mastery, review history,
and `next_review_at`.

### Incorrect Scheduled Review

An incorrect qualifying review must be remediated:

1. Apply `Again` immediately to the authoritative attempt.
2. Show feedback.
3. Schedule a different question at the original requested level for a later
   round.
4. Continue until the learner answers correctly or reaches the retry limit.

Remediation never creates a second FSRS update. It repairs learning after the
authoritative failure.

A remediation attempt served below the requested level is fallback practice and
does not resolve the original remediation requirement.

### Correct Scheduled Review

A correct qualifying review applies `Good` and completes the sense's scheduled
work for the session. It is not repeated in the session merely to fill space.

## Fallback and Qualification

The qualification rule is deliberately simple:

```text
served_level == requested_level -> grade normally
served_level < requested_level  -> practice only
```

A same-level item from a different format is qualifying because every provider
uses the same difficulty scale.

Fallback practice is still delivered and recorded as an attempt, but it does
not:

- Advance an acquisition checkpoint.
- Resolve remediation at the requested level.
- Create an FSRS review log.
- Update stability, difficulty, or mastery.
- Increment FSRS review count.
- Change `last_review_at` or `next_review_at`.

The original requirement remains pending for a later round or session.

## Question Provider Architecture

Question construction and storage are private provider concerns. The learning
domain uses a technology-neutral request/response contract and does not branch
on provider implementation.

All provider calls complete within the calling workflow. The provider contract
does not expose pending jobs or a separate generation lifecycle.

### Provider Descriptor

```text
QuestionProviderDescriptor:
  provider_id
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

### Returned Item

```text
Question:
  question_id
  sense_id
  format_id
  difficulty_level
  interaction_mode: exposure | assessment
  answer_kind
  payload
```

Level 0 uses `interaction_mode = exposure` and has no gradable answer. Levels
1-4 use `interaction_mode = assessment`.

### Provider Interface

```text
QuestionProvider:
  descriptor -> QuestionProviderDescriptor
  prepare(demands: Sequence[QuestionDemand]) -> None
  retrieve(query: QuestionQuery) -> Question | None
```

`prepare` is a session-planning lifecycle hook. A provider receives the demands
relevant to its supported levels and decides how to satisfy them. The learning
domain does not inspect or control that decision.

`retrieve` requests one exact difficulty from one provider. It returns a matching
question immediately or `None`. It does not return a lower-level question; level
fallback belongs to the resolver.

The Python implementation may use `async` methods for I/O, but each call remains
a direct request/response operation.

## Question Resolver

### Resolver Request

```text
QuestionResolutionRequest:
  sense_id
  preferred_format_id
  requested_level
  excluded_question_ids
```

### Resolver Result

```text
ResolvedQuestion:
  question
  requested_format_id
  served_format_id
  requested_level
  served_level
  is_fallback
```

### Resolution Algorithm

For an assessed question, the resolver searches from the requested level down
to level 1:

```text
for level from requested_level down to 1:
    providers = providers supporting level

    if the preferred provider supports level:
        try it first

    uniformly shuffle the remaining providers

    for provider in that order:
        question = provider.retrieve(exact level, excluded ids)
        if question exists:
            return it with requested and served metadata

return None
```

The effective fallback order is:

```text
preferred format at K
other formats at K
preferred format at K-1, when supported
other formats at K-1
...
all formats at level 1
None
```

A final `None` means no provider can supply any eligible item. The session
scheduler defers the requirement and selects another sense; it does not expose
an empty question to the learner.

Level-0 exposure is resolved directly through a provider supporting level 0 and
does not enter the assessed fallback loop.

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

These profiles provide a dominant challenge band plus lower-probability adjacent
levels. They avoid a one-to-one mastery-to-level mapping and prevent abrupt
transitions where every question changes format or difficulty at one threshold.

The planner samples the requested level from the applicable profile. It then
selects a preferred format from providers supporting that level.

Format selection uses a uniform shuffle among eligible providers. Diversity is
stochastic over repeated study and is not forced through persisted recent-format,
recent-level, or coverage counters.

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
NEW_WORD_REQUIRED_CHECKPOINTS = 2
MAX_RETRIES_PER_CHECKPOINT
MAX_EXTRA_QUESTIONS_PER_SESSION
```

The exact retry and extra-question limits are backend policy values. They prevent
one difficult sense from creating an unbounded session.

### Candidate Selection

The planner builds the target set in this order:

1. Unfinished acquisition work carried from prior sessions.
2. Scheduled senses that are due, ordered by lowest retrievability and greatest
   overdue pressure.
3. New senses, within the configured new-word allowance, until the session's
   unique-sense target is filled.

Buried senses are excluded. A sense appears only once in the admitted target set.
Scheduled senses that are not due are not selected by default.

### Base Plan

For each admitted sense, the planner creates requirements rather than locking all
question identifiers:

- New sense: level-0 exposure plus two future level-1 acquisition checkpoints.
- Acquiring sense: remaining level-1 checkpoints.
- Due scheduled sense: one requested level sampled from its mastery profile and
  one preferred format supporting that level.

The plan estimates expected demand per sense, level, and format, then invokes
`prepare` on registered providers with the relevant demands.

Retry requirements are added dynamically after incorrect answers. They preserve
the original requested level and exclude previously served question identifiers.

## Round Scheduling

A round is a variable-size wave with a maximum question count.

Rules:

- A sense appears at most once in a round.
- The scheduler does not introduce every session word in the first round.
- Acquisition checkpoints and retries occur in later rounds, never immediately
  after the originating item.
- A retry waits at least one round, creating intervening practice.
- The scheduler mixes new admissions, due reviews, acquisition checkpoints, and
  eligible retries without exceeding the round maximum.
- Requirements that cannot be resolved are deferred while other senses continue.
- A break is offered after every round.

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
remediation work. The session still has a derived hard ceiling from its backend
safety settings.

## Attempt and State-Update Rules

Every delivered assessment creates an attempt record. State updates depend on
purpose and qualification:

| Purpose | Served at requested level? | Result | State update |
|---|---|---|---|
| Acquisition checkpoint | Yes | Correct | Complete one acquisition checkpoint |
| Acquisition checkpoint | Yes | Incorrect | Keep checkpoint open; schedule later retry |
| Acquisition checkpoint | No | Either | Record fallback practice only |
| Scheduled review | Yes | Correct | Apply one FSRS `Good`; complete review |
| Scheduled review | Yes | Incorrect | Apply one FSRS `Again`; schedule remediation |
| Scheduled review | No | Either | Record fallback practice; review remains due |
| Remediation | Yes | Correct | Resolve remediation; no FSRS update |
| Remediation | Yes | Incorrect | Keep remediation open; no FSRS update |
| Remediation | No | Either | Record fallback practice; remediation remains open |
| Level-0 exposure | N/A | N/A | Mark exposure delivered; no grade or FSRS update |

The durable first-attempt claim remains the guard against duplicate FSRS updates
from concurrent or retried answer submissions.

## Session Completion and Carryover

A session admits the configured number of unique senses, but individual learning
requirements may remain unresolved when safety limits are reached.

At session end, each admitted sense is summarized as one of:

- Acquisition completed.
- Scheduled review completed correctly.
- Scheduled review completed with an authoritative failure and remediation
  completed.
- Acquisition pending.
- Review pending because only fallback practice was available.
- Remediation pending.

Pending acquisition and remediation work carries forward. A session never loops
indefinitely to force a correct answer.

## Provider and Session Invariants

1. Every provider declares exactly which difficulty levels it supports.
2. `retrieve` either returns the exact queried level or `None`.
3. Providers never perform cross-level fallback.
4. Only the resolver performs format and level fallback.
5. The same question identifier is not served twice in one session.
6. A sense is not served twice in one round.
7. Level 0 is always exposure-only.
8. New senses always receive level 0 before any graded checkpoint.
9. New-sense graded checkpoints always request level 1.
10. Acquisition completes after exactly two passed level-1 checkpoints.
11. Only a served level equal to the requested level is qualifying.
12. Fallback practice never updates acquisition or FSRS.
13. A scheduled sense receives at most one FSRS update per session.
14. Remediation never creates an FSRS update.
15. Session retry and total-question work are bounded.

## Integration Boundaries

The design interacts with these existing Pycil responsibilities:

- Session creation and scope validation.
- Sense candidate selection and buried-sense filtering.
- Redis session and round state.
- Durable answer claims and response records.
- FSRS state, mastery projection, and review logs.
- Embedded lexical content and question capabilities.
- Question-format registration and provider resolution.

The learning domain owns:

- Session and round policy.
- Requested difficulty selection.
- Provider ordering and fallback.
- Qualification decisions.
- Acquisition, review, and remediation transitions.
- FSRS update eligibility.

Each provider owns:

- Its format.
- Its supported difficulty levels.
- Its preparation behavior.
- Returning an exact-level question or `None`.

## Observability and Success Metrics

### Learning Outcomes

- First-attempt correctness at the next due review.
- Failure rate at the first scheduled review after acquisition.
- First-attempt correctness by difficulty level and format.
- Same-session remediation success followed by next-review retention.
- Acquisition attempts required per sense.
- Pending acquisition and remediation carryover rates.

### Session Experience

- Sessions completed and abandoned.
- Questions and rounds per session.
- Unique senses per completed session.
- Extra questions caused by retries.
- Time per round and break continuation rate.
- Frequency with which a single sense reaches its retry limit.

### Provider and Resolver Health

- `prepare` duration by provider.
- `retrieve` duration and `None` rate by provider, format, and level.
- Same-level alternate-format resolution rate.
- Lower-level fallback rate and depth.
- Final resolver `None` rate.
- Duplicate-question rate within a session, which should be zero.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Incorrect answers make sessions unexpectedly long | Per-checkpoint retry limits, extra-question ceiling, carryover |
| A provider cannot supply the requested level | Session-time preparation, same-level alternate providers, lower-level practice, defer unresolved requirement |
| Lower-level fallback inflates mastery | Strict equality between requested and served level for qualification |
| Learner memorizes a prompt instead of the sense | Exclude all question identifiers already used in the session |
| New words are treated as durable memories after one easy answer | Level-0 exposure plus two separate level-1 checkpoints before FSRS |
| Question difficulty changes abruptly with mastery | Non-uniform multi-level probability profiles |
| One format dominates through fixed routing | Uniformly shuffled eligible providers at the selected level |
| Production grading becomes a general writing assessment | Level-4 grading is limited to target-sense appropriateness and necessary grammatical or collocational fit |

## Acceptance Criteria

The design is correctly implemented when:

1. A new sense is first delivered as an ungraded level-0 flashcard.
2. A new sense enters FSRS only after two passed level-1 checkpoints in later
   rounds.
3. A failed acquisition checkpoint is retried with a different level-1 question
   and does not erase already completed checkpoints.
4. A due scheduled sense produces exactly one FSRS update from its first
   qualifying attempt.
5. A failed due review is remediated later without a second FSRS update.
6. A question served below the requested level never affects acquisition,
   review count, mastery, or scheduling.
7. Providers expose only descriptor, preparation, and exact retrieval behavior;
   provider internals do not leak into learning policy.
8. Resolver fallback tries all eligible formats at the current level before
   moving to the next lower level.
9. Difficulty after acquisition is sampled from a non-uniform mastery profile,
   not mapped to one fixed level.
10. Format diversity is stochastic and requires no persisted coverage history.
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
session store, learning router, FSRS service, provider registry, schemas,
persistence, and test suites. No implementation should begin before that plan is
reviewed.
