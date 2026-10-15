# Search and content revisions: owning design

**Status:** accepted design, 15 October 2026; implementation acceptance remains pending.

The detailed authority is [search_and_content_revisions.md](../../search_and_content_revisions.md) at the repository root. This navigation page preserves existing architecture links and replaces the earlier replica-sync proposal.

The accepted design uses one PostgreSQL `content_revisions` table with JSON Patch `op` for words, question artifacts and themes, and one lifetime Tantivy writer/poller per index. VPS workers share one directory and owner; Fargate tasks have independent directories and owners. Requests wait for local publication through the same indexing path.

There are no separate search-log/state tables, per-table revision columns, seven-day history pruning, model metadata, extra leader lock, message broker or indexer service. Revision history preserves its baseline and patch chain; index checkpoints are disposable.

Use the root document's [acceptance checks](../../search_and_content_revisions.md#10-implementation-owners-and-acceptance) before enabling mutable replacement overlap or multi-task operation. Infrastructure and lifecycle remain owned by [03](03-hybrid-infrastructure-vps-and-aws-iac.md); delivery/rollback by [05](05-devsecops-cicd-and-walg-backup.md).
