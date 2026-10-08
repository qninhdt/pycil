# Unreleased Lexi dependency

This directory contains the **local, unpublished** enum-capable Lexi wheel used
by Pycil's lockfile, tests and container build. It is not the released `v0.1.0`.
The local version suffix distinguishes it without changing Lexi's published tag,
baseline or checkout version.

- `SHA256SUMS` verifies the wheel bytes before container installation.
- `provenance.json` records the source Git head and hashes of every packaged input,
  including uncommitted source changes. No credentials, reference databases,
  benchmark evidence or test fixtures are packaged.
- The wheel includes Lexi's license and native migration/prompt resources.
- The 2026-10-03 dependency refresh requires stable Tantivy `>=0.26.2,<0.27`
  and SQLAlchemy `>=2.1.3`. The wheel/provenance/checksums were rebuilt from the
  reviewed current checkout; the published Lexi version/tag remains untouched.
- The 2026-10-08 refresh applies [canonical-word-relations.patch](canonical-word-relations.patch):
  deduplicate word relations by resolved target ID and relation type before insertion.
  Distinct relation types and the database uniqueness constraint are preserved.
  Its regression runs native generation and persistence against PostgreSQL in
  [test_learning_pipeline.py](../../apps/api/tests/integration/test_learning_pipeline.py).
- [question-output-validation.patch](question-output-validation.patch) also sends
  question schemas and checks dialogue
  blanks in visible text rather than inflection-tag attributes. Contextual question
  validation runs during SDK parsing, inside the existing bounded LLM retry budget.
  Native regression tests preserve rejection of real blanks, exercise anchored/dialogue
  generation, and verify retry of invalid options before PostgreSQL persistence.
- [generation-tolerance.patch](generation-tolerance.patch) then normalizes known
  generated labels/markup, retains valid individual examples/questions, accepts
  variable batch sizes and removes duplicate questions, including sequential replays.
  It removes the four-request enrichment cap; every sense enrichment starts together.
  Empty usable output still fails inside the bounded LLM retry budget; distractor,
  target, evidence and dialogue validation remain enforced. Pycil's exclusive worker
  owns generation; question deduplication does not add a cross-client database lock.

Rebuild from a reviewed checkout, without inference or publication:

```sh
python scripts/package-lexi.py /explicit/path/to/lexi-ai
```

An existing artifact with different bytes is refused. After reviewing intentional
source changes, pass `--replace`, regenerate `apps/api/uv.lock` with
`uv lock --refresh-package lexi-ai`,
then rerun the library/package and Pycil gates. Never silently replace the wheel
without refreshing its provenance and lock.

To reproduce this refresh, use an isolated copy of the recorded baseline source
inputs, apply the three patches listed above, in order, there with `git apply`, then package
that copy. Do not change the sibling Lexi checkout. `provenance.json` records the
patched input hash as well as the baseline Git head.
