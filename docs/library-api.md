# Library UI read contract

## Deck details

`GET /v1/library/nodes/{id}` returns node metadata, safe breadcrumbs, total
`sense_count`, and for a DECK all `senses`. There is no `sense_page` wrapper. Folder/reference
metadata does not automatically expand every descendant Sense.

`GET /v1/library/nodes/{id}/senses` returns `{senses}` for a deck, without a cursor
or truncation. A nonzero `after_id` returns `422 deck_cursor_not_supported`.
Folder/live-reference scopes return `{senses, next_after_id}` and support
`?after_id=...`, using the last Sense integer ID, not an offset or UUID. Membership
is unordered; scope pagination orders by Sense ID.

```json
{
  "senses": [{
    "sense_id": 1,
    "word_id": 1,
    "lemma": "bank",
    "entry_type": "WORD",
    "pos": "NOUN",
    "tier": "CORE",
    "definition": "a financial institution",
    "cefr_level": "B1",
    "register": null,
    "ipa_uk": "/bæŋk/",
    "ipa_us": null,
    "learning": {
      "state": "DUE",
      "mastery": 50,
      "due_at": "2026-10-02T00:00:00Z",
      "last_rating": "GOOD"
    }
  }]
}
```

For a folder/reference scope, add `next_after_id`, null for the final page.
Neutral saved definitions are used;
missing fields remain null rather than inventing content. State is `NEW`, `DUE`
or `NOT_YET_DUE`, assessed at read time. New mastery is 0; learned mastery is the
configured stability projection, not a fluency score. `learning` is null for an
anonymous viewer and otherwise always belongs to the viewer, never the deck owner.

These fields let the UI render a Sense row, distinguish multiple senses of a word,
show pronunciation/level/progress, open `/v1/words/{word_id}` for full lexical
details, and send the correct integer `sense_id` for membership or learning.
Examples, forms, patterns, collocations, relations and Question pools are omitted
from this list payload. Preparation remains its own learning operation.

## Query and privacy guarantees

- Authorization uses the same live public/inherited/reference rules as study/tools.
  A revoked/private/deleted target returns 404, not empty data or leaked content.
- For an authorized deck, membership uses the `(deck_id, sense_id)` primary key
  directly on a cache miss, otherwise a detached Redis deck snapshot. There is no
  recursive whole-library scope query for deck membership/count.
- Lexi bulk-loads lexical previews through its RAM/cache layer; viewer memory is
  read live in batches. No per-Sense API call or Question/example loading occurs.
- Folder/reference page size is configured in YAML (currently 50). Query counts
  depend on cache state and memory batches; no fixed-count promise is made.
- Pycil's only migration is `0001_baseline`, requiring an empty public schema.
  Membership has no `position`. UUIDv7 applies only to new Pycil UUID identities,
  not Lexi integer IDs or client retry keys.

## Final-state editor

Create with POST; save with PUT at `/v1/library/nodes/{id}`. Existing deck saves
require final `sense_ids`, including `[]` to clear. Submit editable metadata, not
read-only fields. Omitting description or parent clears it. Metadata/membership
commit atomically; the last successful save wins, without ETags or draft merging.
The cap is 200 distinct Senses; existing larger decks allow unchanged/removal-only
membership. Publishing requires explicit `confirm_publication=true`.

See [the complete frontend handoff](frontend-backend-contract.md) for typed response
contracts, auth, errors, study and assistant integration.
