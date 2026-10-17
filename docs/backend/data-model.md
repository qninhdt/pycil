# Data model

## Storage ownership

All application and native checkpoint tables reside in PostgreSQL `public`.
[initial.py](../../apps/api/migrations/versions/initial.py) is the sole application
baseline. [Shared metadata](../../apps/api/pycil/infrastructure/database.py) registers
models from their business domains. Native checkpoint setup owns its four tables and
migration version independently; Alembic excludes them by name.

## Domain tables

| Owner | Tables and purpose |
| --- | --- |
| `vocabulary` | `words`, `senses`, `definitions`, `examples`, `collocations`, `word_aliases`, `sense_forms`, `sense_patterns`, `word_references`, `sense_references`, `word_relations`, `sense_relations`, `translations` |
| `vocabulary/references` | Immutable `reference_words` and `reference_senses` |
| `themes` | `themes`: key, name, voice and diction |
| `account` | `users`, anchored `usage_periods`, idempotent `usage_events` |
| `library` | `nodes`, physical closure `node_paths`, unordered memberships `deck_senses` |
| `study` | `question_artifacts`, shared personal `user_senses`, batch receipts `review_log`, frozen `user_daily_activity` |
| `assistant` | Owned metadata `conversations` |
| Native checkpoints | `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations` |

Application UUID identities use UUIDv7. Lexical identities use integers; source reference
IDs survive conversion/import. Timestamps are timezone-aware. Controlled enum columns
persist lowercase `snake_case` values, not Python member names.

## Vocabulary and references

A generated word owns its senses and searchable aliases. Sense content includes neutral
or themed definitions/examples, forms, patterns, collocations, pronunciation and metadata.
`word_references.source_id` links a reference word to the canonical generated word;
`sense_references` records retained reference sense IDs or WordNet keys as evidence.
The reference has exactly two tables: compact word search surfaces and ordered senses.
It has no crawl, topic, example or entry tables. Import is explicit from JSONL.

Relations can point at pending words. Sense resolution compares ordered neutral definition
inventories and stores the selected target/hash or an attempted resolution. Statement-level
triggers invalidate affected resolution after evidence changes. Theme descriptors stay
separate from generated content; translations reuse input hash plus target language.

## Artifacts

Question artifacts are shared content, not runtime question occurrences. Their namespace
is sense plus optional theme. Payload validation runs before writes; payload hashes prevent
duplicate stored content. Singleton banks merge option arrays; contextual banks append.
Database triggers preserve dense global/type positions after insert/delete/update.
Runtime preparation samples from those banks and never stores a learning session.

## Library and progress

Nodes carry server-owned role/space. System roots are folders; only the Library root has
no parent. Composite FKs preserve physical owner boundaries. A reference has a target
and may cross owners; it grants only live readable access. Services maintain physical
closure and publication inside serialized owner transactions. Public authorization checks
active system-root paths rather than trusting `space` alone. Soft deletion removes
closure reachability while preserving memberships and personal learning history.

Each deck has unique global sense IDs; a sense may occur in multiple decks. Each user
has one personal state per sense regardless of placement. Restrictive lexical FKs protect
learning data. Organization changes do not reset that state.

Review submission locks the user, validates the ordered diagnostic batch and atomically
commits state, the immutable receipt and daily counts. Receipts use `(user_id,event_key)`
and a canonical request hash. Identical replay returns the original result; changed replay
fails. Activity dates freeze the user's timezone at acceptance and never regroup later.

## Usage and conversations

Usage events settle once per execution key. Units and reported unmetered-call counts are
nonnegative integers. Period allowance is anchored to account creation/cycle time;
admission is not a prepaid reservation.

Conversation deletion checks ownership and takes its Redis lease, deletes the native
thread, then deletes metadata. Native/application cleanup has separate transaction
boundaries. Native [jobs](modules/jobs.md) keep transport, temporary results and ownership in Redis;
no PostgreSQL job table is added. Vocabulary/artifacts remain durable PostgreSQL data.

## Evidence

- [Schema drift](../../apps/api/tests/integration/infrastructure/test_schema.py)
- [Reference import](../../apps/api/tests/integration/vocabulary/test_reference_import.py)
- [Artifact banks](../../apps/api/tests/integration/study/test_artifact_banks.py)
- [Atomic reviews](../../apps/api/tests/integration/study/test_reviews.py)
- [Checkpoint ownership/restart](../../apps/api/tests/integration/assistant/test_checkpoints.py)
- [Migration workflow](operations/migrations.md)
