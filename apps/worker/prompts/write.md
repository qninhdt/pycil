{% include "role.md" %}

You will craft a single WRITE question that tests whether a learner can
recall the meaning of a target word/phrase in their own words.

CONSTRAINTS:
- `prompt`: a clear English question, e.g. "Define <term>." or
  "What does <term> mean?" (≤ 200 chars).
- `expected_answer`: the canonical short definition (≤ 80 words).
- `alt_answers`: 1-3 acceptable paraphrases of the expected answer.
- `explanation`: ≤ 200 chars explaining why the expected answer is right.

Return JSON:
{
  "prompt": str,
  "expected_answer": str,
  "alt_answers": [str, ...],
  "explanation": str
}

Term: {{ term_value }}
Definition (canonical): {{ definition_text }}
