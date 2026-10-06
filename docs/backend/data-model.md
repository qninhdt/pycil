# Data model

This page describes the working-tree schema. Application migration head is
`0005_profile_handle_bio`; no production migration is implied.

## Ownership boundaries

| Schema / artifact | DDL owner | Purpose |
| --- | --- | --- |
| PostgreSQL `public` | Pycil Alembic migrations | Users, Library, learning, usage, conversation metadata, generation queue |
| PostgreSQL `lexi` | Vendored Lexi migrations | Shared words, senses, definitions, examples and question artifacts |
| PostgreSQL `checkpoints` | Native LangGraph checkpoint setup | Conversation state, messages, interrupted approvals |
| Cambridge SQLite file | External reference dataset | Selectable reference entries used by native Lexi |

Pycil imports `lexi.senses` into its metadata to resolve cross-schema FKs. That is not
permission for Pycil Alembic to manage Lexi tables. Migration filtering excludes externally
owned tables. All three PostgreSQL version owners are verified at startup.

## Application table inventory

| Table | Identity | Responsibility |
| --- | --- | --- |
| `users` | UUID PK; unique Clerk subject / optional handle | Plan, sparse settings, cycle anchor, handle/bio/display identity |
| `nodes` | UUID PK; unique `(owner_id, id)` | Physical folder/deck/reference identity and placement |
| `node_paths` | `(ancestor_id, descendant_id)` PK | Physical transitive closure with depth |
| `deck_senses` | `(deck_id, sense_id)` PK | Unordered final deck membership |
| `user_senses` | `(user_id, sense_id)` PK | Current shared personal FSRS state |
| `review_log` | `(user_id, event_key)` PK | Immutable ordered batch hash/result and accepted day |
| `user_daily_activity` | `(user_id, day)` PK | Durable applied/practice counts, independent of membership |
| `usage_periods` | UUID PK; unique `(user_id, period_start)` | Anchored allowance and accumulated consumption |
| `usage_events` | UUID PK; unique execution key | Idempotent assistant usage settlement |
| `conversations` | UUID PK | Owner, title, creation/update timestamps |
| `word_generations` | UUID PK; unique `(available_id, target)` | Shared generation job state and retry bookkeeping |

Application UUID defaults use UUIDv7; roots introduced by the SQL data migration use
database-generated UUIDs. Lexical senses/questions use integer identities. Timestamps
are timezone-aware; normal event calculations use UTC before reporting conversions.

## Nodes and closure

`NodeType` is FOLDER, DECK, or REFERENCE. `NodeRole` is NORMAL, LIBRARY_ROOT,
PERSONAL_ROOT, or PUBLISHED_ROOT. `NodeSpace` is LIBRARY, PERSONAL, or PUBLISHED.
Role and space are server-owned fields, not request-editable visibility.

Structural guarantees include:

- Exactly one role of each system kind per owner via a partial unique owner/role index.
- System nodes must be folders; only Library roots have null parents.
- An owner-preserving composite parent FK; parents must additionally be folders by service validation.
- REFERENCE iff a target is present; self-parent and self-reference are forbidden.
- References may cross owners; physical parents may not.
- Library depth is 0, Personal/Published depth is 1, and normal children start at depth 2.

Closure stores only physical paths, including a depth-0 self-path for active nodes. A
move keeps internal subtree paths, replaces outside ancestor paths, and updates derived
space in the same transaction. A subtree soft delete marks nodes inactive and explicitly
removes their effective paths. It does not delete memberships or personal learning state.

Closure and space invariants are maintained by shared services, not a database trigger
repair system. Do not bypass them with direct application SQL. `space=PUBLISHED` alone
is not sufficient for public access: authorization verifies active system-root paths.

## Membership and learning

Membership has no per-user copy or position column. Each deck selects global sense IDs.
Repeated senses in different decks are legal; one deck cannot have duplicate IDs.
Sense FKs use RESTRICT so removing shared lexical content cannot silently erase learning.

`user_senses` stores stability, difficulty, last review, due time, last rating, review
and lapse counts, and timestamps. Stability/difficulty must be positive; review count
is positive and lapse count is nonnegative. References and organizational changes do
not create or delete this state. No state row means New.

`review_log` stores request SHA-256, acceptance timestamp, frozen local day and JSONB
original batch result. Retention lasts until account deletion; no source/session data.
Daily counts commit atomically with accepted batches. Streaks derive from active days,
not persistent counters. There is no backend learning-session table.

## Usage, conversations, and generation

Usage period counts and units are nonnegative. Settled events point to a period and
record feature, units, reported-unmetered call count, and occurrence time. Reading an
allowance does not require creating a period row.

Conversation metadata is application-owned; native messages and approval interrupts
live in `checkpoints`. Deleting a conversation explicitly cleans the native thread before
deleting metadata. This is not an atomic cross-schema application transaction.

Generation rows have no `user_id`: jobs are shared for a selected lexical handle/target.
`word_id` is a nullable integer, not an application-declared FK. Status is QUEUED,
RUNNING, SUCCEEDED, or FAILED. Stage, attempts, next-attempt time, and sanitized error
support finite retries and crash recovery.

## Important access indexes

| Index shape | Consumer |
| --- | --- |
| Active nodes `(owner_id, parent_id, created_at, id)` | Child listing and owned placement reads |
| Nodes `parent_id`, `reference_id` | Physical relationships and target lookup |
| Active Published normal nodes `(created_at, id)` / `(owner_id, created_at, id)` | Discovery catalog ordering |
| Generated weighted `search_vector`, GIN | Scoped node FTS and public Discovery |
| Paths PK plus `(descendant_id, ancestor_id)` | Subtree expansion and ancestor authorization |
| Membership PK plus sense index | Deck selection and lexical associations |
| Memory `(user_id, due_at, sense_id)` | Due selection |
| Activity PK `(user_id, day)` | Private daily grid / lifetime active days |
| Conversations `(user_id, updated_at, id)` and `(updated_at, id)` | Owner pagination and retention |
| Generation `(status, next_attempt_at, created_at, id)` | Eligible job claim ordering |

FTS vector uses explicit `simple` configuration: name A, nullable description B,
stored generated transactionally. No copied lexical payloads, user node preferences,
tags/translation tables, mastery index or raw history index is introduced.

## Sources and verification

- Models: [account](../../apps/api/pycil/account/models.py), [Library](../../apps/api/pycil/library/models.py), [study](../../apps/api/pycil/study/models.py), [assistant](../../apps/api/pycil/assistant/models.py), [vocabulary](../../apps/api/pycil/vocabulary/models.py)
- [Baseline](../../apps/api/migrations/versions/0001_baseline.py), [placement migration](../../apps/api/migrations/versions/0002_nodes_spaces_paths.py)
- [Fresh schema tests](../../apps/api/tests/integration/test_fresh_schema.py) and [populated upgrade tests](../../apps/api/tests/integration/test_nodes_migration.py)
- Upgrade/backup safety: [Migrations](operations/migrations.md)
