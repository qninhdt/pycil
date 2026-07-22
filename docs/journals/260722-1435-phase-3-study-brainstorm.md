# Journal Entry: Phase 3 Spaced Repetition Learning Brainstorming

- **Date**: 2026-07-22
- **Topic**: Phase 3 Spaced Repetition Learning (`/study` & `/study/[sessionId]`) Brainstorming
- **Design Document**: `docs/designs/phase-3-spaced-repetition-study.md`

## Summary of Decisions
1. **API Integration**:
   - `POST /v1/sessions` to start session.
   - `GET /v1/sessions/{id}/next` to retrieve active question or handle generation polling (`pending`) or session completion (`exhausted`).
   - `POST /v1/answers` to submit answers.
   - `GET /v1/responses/{id}` polling for async AI sentence grading (`use_in_sentence`).
2. **Question Component Suite**:
   - `DefinitionMcqCard`: 4 options for vocabulary definitions.
   - `ContextualMcqCard`: 4 options for context fill-in.
   - `ClozeCard`: Direct text input for cloze blanks.
   - `UseInSentenceCard`: Textarea input for custom sentence writing.
3. **Session Summary**:
   - Hero celebration screen when `next` returns `exhausted`.
   - Summary statistics: cards completed, accuracy %, mastered count.

## Next Action
- Invoke `/ck:plan` with context `docs/designs/phase-3-spaced-repetition-study.md`.
