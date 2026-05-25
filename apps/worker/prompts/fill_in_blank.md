{% include "role.md" %}

You will craft a single FILL-IN-BLANK question by selecting an example
sentence that uses the target word/phrase, replacing the headword (or
its inflection) with `___`.

CONSTRAINTS:
- `prompt`: a single sentence with EXACTLY one `___` token.
- `expected_answer`: the missing word, lowercased, single-word.
- `alt_answers`: alternate inflections (e.g. plural, past tense) — max 3.
- `explanation`: ≤ 150 chars on why this word fits.

Return JSON:
{
  "prompt": str,
  "expected_answer": str,
  "alt_answers": [str, ...],
  "sentence_id": null,
  "explanation": str
}

Term: {{ term_value }}
Definition (canonical): {{ definition_text }}
