# Technical Design: Phase 3 Spaced Repetition Learning (/study & /study/[sessionId])

## 1. Executive Summary & Objectives
Phase 3 delivers the core spaced repetition learning experience for Pycil using the FSRS 4.5 algorithm. Users can view decks due for study on `/study`, start a learning session (`POST /v1/sessions`), and play through questions interactively on `/study/[sessionId]`.

## 2. System Architecture & Component Breakdown

### 2.1 Backend API Integration (`apps/api/pycil/learning/router.py`)
- `POST /v1/sessions`: Starts session for a given `node_id`, initializes Redis session queue. Returns `{ sessionId, queueSize, firstState }`.
- `GET /v1/sessions/{id}/next`: Fetches next question. Returns:
  - `{ state: "pending", senseId, recommendedType }`: Question generation in progress. Client retries after 1.5s.
  - `{ state: "ready", questionId, senseId, format, payload }`: Active question payload.
  - `{ state: "exhausted" }`: Queue finished, transition to Session Summary.
- `POST /v1/answers`: Submits user answer `{ sessionId, questionId, answer }`. Returns `GradeResponse`:
  - `gradeStatus: "graded"` for synchronous formats (`definition_mcq`, `contextual_mcq`, `cloze`).
  - `gradeStatus: "pending"` for asynchronous format (`use_in_sentence`).
- `GET /v1/responses/{id}`: Polls response verdict for pending async AI grading.

### 2.2 Client-Side Components (`apps/web/components/study/`)
- `StudyDeckGrid.tsx`: Deck card list showing deck info, total items, learned/mastered count, and "Bắt đầu học" button.
- `QuestionPlayer.tsx`: Main container managing state machine (`FETCHING` → `READY` → `SUBMITTING` → `GRADING_PENDING` → `FEEDBACK` → `EXHAUSTED`).
- `DefinitionMcqCard.tsx`: MCQ for definitions (4 options).
- `ContextualMcqCard.tsx`: MCQ for fill-in-the-blank in context.
- `ClozeCard.tsx`: Text input for cloze tests.
- `UseInSentenceCard.tsx`: Rich sentence writing textarea with AI evaluation indicator.
- `FeedbackBanner.tsx`: Grade result indicator (Correct/Incorrect badge, score, mastery change `masteryBefore` → `masteryAfter`, feedback text, and "Tiếp tục" button).
- `SessionSummary.tsx`: Summary screen showing completed cards count, accuracy %, mastered count, and navigation actions.

### 2.3 Server Actions & API Layer (`apps/web/lib/actions/study.ts`)
- `startStudySession(nodeId: string)`
- `getNextQuestion(sessionId: string)`
- `submitAnswer(sessionId: string, questionId: string, answer: string)`
- `getResponseVerdict(responseId: string)`

## 3. Data Flow & State Machine

```
   [Select Deck]
         │
  POST /v1/sessions
         │
 ┌───────┴───────┐
 │               │
[ready]      [exhausted]
 │               │
 │        Session Summary
 ▼
GET /v1/sessions/{id}/next
 ├─ pending ────► Polling retry (1.5s)
 ├─ ready ──────► Render Question Card (MCQ / Cloze / Sentence)
 │                     │
 │               User Submits
 │                     │
 │               POST /v1/answers
 │                     │
 │        ┌────────────┴────────────┐
 │    [graded]                  [pending]
 │        │                         │
 │        │                Poll /v1/responses/{id}
 │        │                         │
 │        └────────────┬────────────┘
 │                     ▼
 │               Feedback Banner
 │                     │
 └────── [Next] ───────┘
```

## 4. Acceptance Criteria
1. `/study` page lists user's decks with stats and functional "Bắt đầu học" button.
2. Clicking "Bắt đầu học" creates a session and redirects to `/study/[sessionId]`.
3. Question player renders all 4 question formats accurately without leaking correct answers in DOM/payload.
4. Synchronous answers display feedback instantly; `use_in_sentence` polls verdict until AI grading completes.
5. `exhausted` state triggers clean Session Summary view with stats and return options.

## 5. Next Steps
- Run `/ck:plan` to generate implementation plan for Phase 3.
