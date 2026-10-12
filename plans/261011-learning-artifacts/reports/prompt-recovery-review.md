# Prompt recovery and learning change review

Prompt recovery is complete. Rich original generation instructions were recovered from Lexi Git HEAD, renamed or merged to match the six artifact contracts, and adapted to their new inputs and payloads. Original single-word and definition grading resources are unchanged; usage grading changes only its accepted Boolean axes. Sentence Rewrite is a new task and retains the original usage constraints alongside its accepted meaning-preservation rules.

Reviewed the connected native artifact generation/storage/grading flow, Pycil preparation/tracking and frontend session/settings consumers. Expected load is up to 20 Senses with 3 questions each; request concurrency remains controlled by the native provider limit. No new full scans or per-question database reads were identified in preparation/tracking.

## Functional findings — resolved

1. **Dialogue validation rejects correctly tagged multiword targets.** Lexi `lexi_ai/questions/schemas.py:180` counts markup spans, although the existing tagging resource requires separate tags for fixed components. A conversation containing `I [brought|p] the budget [up] yesterday.` once raises `Conversation must contain one marked target`. Count complete target occurrences rather than individual tags, preserving the existing tagging contract. Leaving this rejects valid phrasal-verb/idiom artifacts and wastes generation requests.

2. **Context-word-meaning validation rejects licensed slot realizations.** Lexi `lexi_ai/questions/schemas.py:162` removes slots from the citation and then compares that sequence with an answer containing realized slot values. `cross {one's} fingers` with the supplied past form `crossed {one's} fingers` rejects `crossed her fingers`, although existing `lexi_ai/patterns.py:58` accepts that realization. Reuse the licensed pattern matcher for complete answer forms. Leaving this blocks valid Cloze and Meaning in Context artifacts for expressions with slots.

3. **Missing review reference fields produce HTTP 500.** Pycil `apps/api/pycil/study/schemas.py:116` indexes `format` and `question_type` inside a before-validator before required-field validation runs. A review item with diagnostics but either field omitted raises `KeyError`; a FastAPI test endpoint returns 500 for both cases. Allow ordinary required-field validation to handle missing keys. Leaving this turns invalid client requests into server failures.

4. **Free settings are checked against saved Pro formats before effective formats.** Pycil `apps/api/pycil/account/schemas.py:138` validates stored pair feasibility before `effective_learning` replaces formats with quiz-only. Starting from saved `DEFINITION_TO_WORD + SINGLE_WORD`, a Free user changing only the type to `MEANING_IN_CONTEXT` receives `invalid_preferences`, while the frontend enables Save and the effective `MEANING_IN_CONTEXT + SINGLE_CHOICE` pair is supported. Separate structural saved-preference checks from effective plan feasibility, preserving saved Pro format preferences. Leaving this prevents valid Free settings updates after downgrade.

## Cleanup findings — resolved

5. **Unused preparation hook.** `apps/web/src/hooks/use-learning.ts:46` exports `usePrepareSession`, but repository searches find no caller in source, tests or E2E. The active QuizFocus preparation path calls the learning service directly. Delete the hook and its now-unused imports. Leaving it maintains an unused second entry point for the same action.

6. **Dead eager-question generation feedback.** `apps/web/src/components/dictionary/dictionary-page.tsx:97` and `:107` still handle a `PARTIAL` stage and describe unavailable question types. Real Word generation now emits `WORD` or `READY`; the preview dictionary also never emits `PARTIAL`. Delete both retired branches. Leaving them suggests the removed question-readiness flow still exists.

7. **Duplicated usage rules in the new rewrite prompt.** Lexi `lexi_ai/questions/prompts/types/word_to_usage.jinja:16` and `types/sentence_rewrite.jinja:19` contain the same 13-line block of usage-error and target-tagging guidance. A future correction to those shared rules currently requires two edits. Move the unchanged common prose to a shared Jinja include, keeping task-specific rules in their existing files. Leaving it risks the two tasks drifting; the domain instructions themselves must be preserved.

The settings UI omitting Sentence Rewrite is an accepted deferral in the design, not a finding. `remove_positions` is called by schema teardown and is not dead code. Historical benchmark question IDs remain evidence metadata rather than persisted runtime question storage.

## Original review verification

- Prompt recovery: 73 native tests passed, including rendering, Theme activation, artifact contracts, usage and distribution checks.
- Updated native wheel: checksum passed, Pycil lock refreshed and installed; all 16 prompt resources match native source byte for byte.
- Pycil native-consumer integration: 14 tests passed; disposable test stores were removed.
- Ruff checks on touched Python tests and scoped Git whitespace checks passed.
- Functional findings 1–4 were reproduced directly; dead-code findings were checked against their real callers and stage producers.

Original verdict: fix 1–4 before calling the learning implementation complete. Findings 5–7 are cleanup, with approximately 19 lines removable by deleting unused code and sharing existing prose.

Not checked: paid model inference, production migration/deployment and live Clerk/browser journeys. Existing passing tests do not cover the four reproduced failures.

## Resolution

All seven findings are fixed. Dialogue validation counts complete licensed expressions across split tags; Context Word Meaning reuses the existing slot matcher with licensed head inflections. Review DTOs leave missing fields to required-field validation. Stored preference structure and limits remain validated, while pair feasibility follows effective plan formats; the frontend preview adapter uses the same rule. The unused hook and PARTIAL branches are deleted. Usage and Rewrite generation share an include whose rendered prose is unchanged word for word.

Sentence Rewrite additionally uses JSON-e conditionals in `grade_word_to_usage_2.json` for Source and meaning preservation. The standalone meaning-preservation file and Python assembly are removed. The criterion text is unchanged and both tasks still use at most two decision calls.

Regression checks cover multiword tagging, repeated/incomplete targets, realized slots and inflections, missing HTTP fields, downgraded Free preferences, preview preparation, conditional grading and untrusted Source text. The content-generation test fixture now reads the restored artifact-context wrapper instead of raw JSON; its unused raw-JSON parser path is removed.

- API: 301 passed, 2 opt-in profiles skipped; all 14 learning integrations passed again with the rebuilt native package.
- Frontend: 17 learning/dictionary tests and 13 service tests passed; TypeScript and scoped lint passed.
- Native focused verification: 70 prompt/artifact/usage tests and 82 prompt/benchmark tests passed.
- Final native suite: 685 passed, 57 environment-dependent tests skipped. All benchmark callers and the cancellation/resume test passed.
- Packaging: checksum verified, lock refreshed, package reinstalled; all 16 question prompt resources and grading/validation source match the native checkout. The deleted standalone grading resource is absent.

One earlier full native run hit `SQLite checkpoint busy` in the existing cancellation/resume test. The isolated test and final full suite passed on rerun; no checkpoint check was disabled or error swallowed. The intermittent cleanup failure was observed but is not claimed fixed.

Verdict: all seven reviewed findings and the requested JSON-e consolidation are resolved.

Not checked: paid inference, production migration/deployment and live Clerk journeys.
