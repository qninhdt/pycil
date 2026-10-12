# Unreleased Lexi dependency

This directory contains the local, unpublished Lexi wheel used by Pycil's lockfile,
tests and container build. The local version suffix distinguishes it from the
published package without changing the sibling checkout's version/tag.

- `SHA256SUMS` verifies the wheel bytes before container installation.
- `provenance.json` records the source Git head and hashes of every packaged input,
  including uncommitted source changes. Credentials, databases, benchmark evidence
  and tests are not packaged in the wheel.
- The wheel includes the installed `lexi` CLI and native migration/prompt resources.
- Packaging copies the current Lexi source without patches. Canonical relation
  deduplication, validated question output, generated-label/markup normalization,
  usable-example/question filtering and duplicate-question suppression now belong
  to Lexi itself. Native and Pycil generation use the same implementation.
  Schema failures feed the latest field errors into the existing bounded same-model
  retries; task instructions and source data are preserved, validation remains strict.
- Every Lexicon defaults to 128 concurrent provider operations. CLI Word
  generation runs up to 128 words concurrently; the maintainer script defaults to
  32 concurrent Words. Sense enrichment and question banks
  share that instance's request limit. Pycil's API process runs up to
  128 word jobs concurrently and uses the same request limit for all their banks.

Rebuild from the reviewed checkout, without inference or publication:

```sh
python scripts/package-lexi.py /explicit/path/to/lexi-ai
```

An existing artifact with different bytes is refused. After reviewing intentional
source changes, pass `--replace`, refresh `apps/api/uv.lock` and rerun package and
consumer checks. No wheel-only source edits or patch files are maintained.

The current suffix is `+pycil.20261011`, the native baseline is
`20261009_base`, and the current head is `20261012_word_refs`.
Reference inflections are imported and searched with FORM rank. Upgrading a database
that lacks their table triggers one reference reimport through the migration gate.
The compact-content migration converts stored examples/questions to `[surface]` /
`[surface|code]` markup and drops unused relation glosses. Enrichment runs concurrent
batches of up to eight Senses, requesting three examples per Sense by default.
Inventory references are grouped by part of speech. Sense DTOs and enrichment no
longer expose usage notes; the native migration drops stored `usage_note` values.
Downgrading can restore the nullable column but cannot recover those values.
Old wheel artifacts are removed; the native migration chain remains packaged.
Required reference is imported into PostgreSQL `lexi_reference` by the setup gate;
the bundled `content.sqlite` seeds words/artifacts automatically through the same
setup gate. `CONTENT_SHA256SUMS` verifies this standalone snapshot separately from
the wheel; both ship in the backend image. API startup reads PostgreSQL and never
downloads/imports SQLite. Replace the snapshot and refresh its checksum together
when promoting new generated content; imports preserve IDs and reject conflicts.
Cambridge and optional WordNet remain distinct private reference providers.
WordReference maps resolved Cambridge entries to canonical Words. Normalized input
that resolves to a completed Word adds the link before enrichment and reuses content.
The reference-rename migration preserves link IDs and every lexical row.

The artifact migration replaces old question storage and preserves lexical tables. Lexi stores six artifact kinds for eight public question types; typed grading reads artifacts, while Pycil constructs runtime samples and grades quizzes locally.
