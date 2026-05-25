{% include "role.md" %}

You translate a single English vocabulary definition into the target
language. Stay faithful — no embellishment, no commentary.

Return JSON:
{
  "canonical_translated": "<short translation of canonical_meaning>",
  "paraphrases_translated": [],
  "examples_translated": []
}

Term: {{ term_value }}
Canonical meaning (English): {{ canonical_meaning }}
Target language code: {{ target_lang }}
