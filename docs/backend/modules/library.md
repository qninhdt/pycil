# Library, publication, references, and scopes

## Responsibility and invariants

Library owns physical nodes, deck membership, system roots, closure maintenance, and
live read/edit authorization. Learning state belongs to the user/sense pair in study;
Library placement is not a second progress identity.

```text
Library [owner-only, depth 0]
├── Personal [owner-only, depth 1]
│   └── normal folders / decks / references
└── Published [publicly readable, depth 1]
    └── normal folders / decks / references to published targets
```

System identity is role/ID based, never determined by names. Normal content cannot
live directly under Library. Omitted/null parent on create resolves to Personal.
All ordinary editing/deleting is owner-only and rejects system nodes.

## Current API

Read, creation, targeted metadata/membership writes, move/publication and subtree copy
are implemented. The frontend and assistant use these same targeted contracts.

| Operation | Contract |
| --- | --- |
| `GET /v1/nodes` | Child metadata page; default authenticated scope is Library |
| `POST /v1/nodes` | Create normal folder/deck/reference; return saved metadata and deck IDs |
| `GET /v1/nodes/{node_id}` | Metadata, safe breadcrumbs, reference availability; no senses/counts |
| `PATCH /v1/nodes/{node_id}` | Edit name and/or description without replacing membership |
| `POST /v1/nodes/{node_id}:modifySenses` | Atomic add/remove of deck sense IDs |
| `POST /v1/nodes/{node_id}:move` | Move without replacing metadata/membership; explicit publication consent and optional retained reference |
| `POST /v1/nodes/{node_id}:copy` | Atomically copy an owned normal subtree into an owned folder |
| `DELETE /v1/nodes/{node_id}` | Soft-delete owned normal subtree; 204 |
| `GET /v1/nodes/{node_id}/senses` | Same paginated lexical/learning response for every node type |
| `GET /v1/nodes/{node_id}/senses/{sense_id}/sources` | Scope-local authorized provenance overflow |
| `GET /v1/nodes/{node_id}:search` | Name/description FTS within container/reference scope |
| `GET /v1/discovery/nodes` | Public catalog browse/search, owner/type filters |

### Targeted writes

`POST /v1/nodes/{node_id}:modifySenses` accepts `{"add":[123],"remove":[456]}` and
returns saved deck metadata with the resulting complete `sense_ids`. Both arrays
are bounded to 1,000 distinct strict positive IDs. Overlapping IDs are rejected.
The owner lock serializes the delta against current membership before applying
existing sense/quota validation; adding a present member or removing an absent
one is idempotent. Unrelated concurrent membership changes are preserved.

Metadata PATCH accepts only supplied `name`/`description`; omission preserves a
field and `description: null` clears it. It cannot move a node or replace senses.
Empty patches and blank/null names are rejected.

Move accepts `parent_id`, `confirm_publication` and `retain_personal_reference`.
It enforces destination/cycle/depth/publication rules. Copy accepts
`parent_id` and `confirm_publication`, returns the new root, and runs the entire
physical subtree in one owner-locked transaction. Deck memberships are independent;
references to copied internal targets are remapped to their copies. External targets
retain live authorization checks. Quota or publication failure rolls back every copy.

There are no mutable visibility flags or old collection/library-route aliases. Role,
space, owner, and type changes cannot be supplied through metadata edit. Reference target is immutable.

## Live authorization

Read requires an active physical path to the owner's Library and either current
ownership or an active Published-root path. Deleted/detached nodes and paths crossing
deleted ancestry do not grant read access. `space=PUBLISHED` is an index/derived field,
not the security authority. Normal owner edits also reject corrupted space/path disagreement.

Owners see full private breadcrumbs. Visitors see breadcrumbs starting at Published;
the Published detail has no exposed navigable private parent. Public-safe profile
provides the starting Published ID. Unreadable guessed IDs return `node_not_found`.
Breadcrumbs include the current node as their final entry. UI paths that append the
current node themselves must first exclude that entry.

Anonymous listing requires an explicit public parent. A reference to a folder can be
used as `parent_id`: the server resolves it and lists the target's immediate children.
A reference to a deck is a learning/sense scope, not a folder child list.

## Create and targeted edits

Create an empty Personal folder:

```json
{"type": "FOLDER", "name": "Work vocabulary"}
```

Create a deck using real existing lexical sense IDs:

```json
{"type": "DECK", "name": "Meetings", "sense_ids": [1, 2]}
```

Create a reference by supplying `type=REFERENCE` and a readable folder/deck's UUID as
`reference_id`. Reference-to-reference targets are rejected. Containers cannot contain
`sense_ids`. Names are nonblank up to 255 characters; description is up to 8,000.

Targeted membership edits validate new sense existence and quota growth under the owner
lock. Metadata edits change only supplied fields. The move operation preserves
the current cycle, destination, publication and retained-reference checks.

## Publication boundary

Publishing is a move to Published or one of its folders, not a separate visibility API.
The move operation takes the Published destination, `confirm_publication=true`,
and optionally `retain_personal_reference=true`.

- Entering Published needs consent; leaving it does not need subscribers' permission.
- The canonical node/subtree IDs and memberships are preserved.
- A retained reference is created at the old Personal parent; `retained_reference_id`
  is returned. This consumes another owned-node slot.
- When publishing a reference, the retained placement points to its original folder/deck,
  not to the wrapper reference.
- Publication validates references anywhere in the moving subtree. Same-subtree targets
  can become public atomically; external private targets cannot.
- Derived space and closure paths update in the same transaction.
- Unpublish moves into Personal. Existing foreign references are not synchronously rewritten;
  live access checks make their targets unavailable.

Reference target availability is stricter inside Published: it must be currently public
even when the viewer owns that private target. An owner's private privilege cannot make
public scope counts differ by following a forbidden private target.

Owner metadata can show an unavailable wrapper with `reference_available=false` and
`reference_id=null`. Visitor lists omit unavailable references, and visitor direct
reads fail. Unavailable expansion contributes nothing to the readable scope; this is
not the same as silently truncating an oversized authorized scope.

## Closure, cycles, and deletion

`node_paths` stores physical ancestor/descendant distance only. Create adds self and
parent-ancestor paths. Move rejects a destination inside the subtree, removes old
outside paths, combines destination ancestors with internal subtree paths, and preserves
internal paths. Direct ancestor-reference checks also inspect references inside a moved subtree.

Physical cycles, direct self-reference, and direct reference-to-ancestor violations are
rejected. Indirect reference cycles can exist; live expansion uses visited node IDs.
Reference hops do not consume the physical depth quota. Tests include 25 logical hops
with all physical placements no deeper than 3.

Delete marks the owned subtree inactive and removes its effective closure rows.
Memberships and personal progress are not cleared; active queries and quota counts
exclude deleted nodes. A saved foreign wrapper may remain active while its target is unavailable.
No restore API is implemented.

## Scope engine and limits

`scope.scope_ids()` authorizes a starting node (or resolves whole Library), expands
physical closure, batches valid reference edges, and stores viewer-local metadata and
adjacency. It returns a distinct sense SQL selection over deduplicated deck IDs; it
does not hydrate all senses into Python.

`resolve_scopes()` jointly authorizes requested roots and reference frontiers, returns
root-to-node/deck projections, and keeps sense sets in SQL. `ScopeBudget` shares physical
work across one request. Card summaries additionally guard distinct-scope logical
membership projection; identical scopes are computed once. Batch summaries and inline
`include=summary` on child/catalog pages use the same bounded service.
Do not persist or reuse a budget across users, requests, or mutations as an access cache.

| Guard | Current value / interpretation |
| --- | --- |
| Physical depth | 20 from Library at depth 0 |
| Deck size | 1,000 senses |
| Immediate children | 500 per destination folder |
| Owned active nodes | 2,000; includes Personal/Published, excludes Library only |
| Owned active memberships | 100,000 before deduplication across decks |
| Scope expanded nodes | 10,000 distinct metadata nodes |
| Scope memberships | 200,000 across deduplicated decks, before sense DISTINCT |
| Scope deadline | 5 seconds for expansion; statement timeout 3 seconds |

Metadata reads use remaining-budget + 1 bounds, and membership guards cap rows before
counting. A too-large scope raises 422 `scope_too_large` with no partial result.
Expansion deadline/cancellation raises 503 `scope_timeout`; later request SQL cancellation
can raise `query_timeout`. The overall expansion deadline is not an end-to-end HTTP SLA.

Quotas serialize under the owner lock. Existing over-limit migrated data is kept:
depth repair and membership reductions remain possible, while growth in constrained
dimensions is rejected. Foreign expansion does not count against ownership, but may
exceed work budgets. Whole-Library tracking includes both spaces and readable references;
historical progress outside Library is not automatically included.

## Browsing

Child pages sort creation time/ID; opaque tokens bind the requested parent/viewer without
reopening a deleted anchor. Sense pages support literal case-insensitive lemma `q`, state
filters, ID/lemma/last-review sorts, `cursor`, `limit` and optional `include=examples,sources`.
Filters/order precede LIMIT. Last-review means applied FSRS review, not early practice.
Source decks are unique canonical decks in this scope, up to 5 inline with count/overflow;
each source includes `owner_id` and `space` so clients can link to its canonical Personal or Published route.
examples use one native page batch, up to 2 each. No per-sense SQL/HTTP enrichment loop.
Missing native content raises `learning_content_changed`. `as_of` freezes classification
within cursor traversal, not a membership snapshot. Anonymous personal fields are null.

Scoped FTS matches node names/descriptions using `simple`, name weight A, description B,
GIN and `websearch_to_tsquery`/`ts_rank_cd`. A deck is not a node-search container. Discovery
returns active NORMAL Published nodes with authoritative root-path checks, excludes
unavailable public references, and does not expand the whole global catalog to paginate.
Catalog without `q` browses newest first; FTS uses rank/ID. No popularity counts, tags,
autocomplete/fuzzy promise or exact global result count is added. Broad rank queries
still depend on candidate count and are subject to deadlines.

## Failure codes and evidence

Important codes: `node_not_found`, `system_node_protected`, `invalid_parent`,
`invalid_tree_space`, `node_cycle`, `node_depth_exceeded`, `invalid_reference_target`,
`reference_unavailable`, `publication_confirmation_required`,
`private_reference_cannot_be_published`, `invalid_retained_reference`, `quota_exceeded`,
`deck_sense_limit_exceeded`, `deck_membership_required`, `sense_not_found`, and scope errors above.

- [Router/schemas](../../../apps/api/pycil/library/api.py), [schemas](../../../apps/api/pycil/library/schemas.py)
- [Shared mutation service](../../../apps/api/pycil/library/nodes.py), [authorization](../../../apps/api/pycil/library/access.py)
- [Closure](../../../apps/api/pycil/library/tree.py), [scope](../../../apps/api/pycil/library/scope.py), [sense pages](../../../apps/api/pycil/library/senses.py)
- [Library integration](../../../apps/api/tests/integration/test_library.py)
