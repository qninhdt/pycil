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

Rebuild from a reviewed checkout, without inference or publication:

```sh
python scripts/package-lexi.py /explicit/path/to/lexi-ai
```

An existing artifact with different bytes is refused. After reviewing intentional
source changes, pass `--replace`, regenerate `apps/api/uv.lock` with `uv lock`,
then rerun the library/package and Pycil gates. Never silently replace the wheel
without refreshing its provenance and lock.
