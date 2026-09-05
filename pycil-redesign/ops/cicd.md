# ops/cicd

Two workflows. Decisions `N6`–`N9`.

## 1. Shape

```text
PR        lint · typecheck · unit · integration · agent contract · golden journey · build
deploy    manual or tag → push by digest → pull → migrate → up → health gate → smoke
```

Two, down from three (`N6`). The third was a nightly real-model evaluation that
**skipped its only real work on every run**, because the repository holds no
provider secret — a green badge for work that never happened. Under `N3` that
outcome is a failure, not a pass.

Measurement returns when there is a secret and a budget to cap it, as a recorded
number rather than a gate (`N4`).

## 2. The PR gate

```text
1  lint · format · typecheck            all languages
2  unit                                 no external dependency
3  integration                          Postgres + Redis via containers   (N2)
4  agent contract                        scripted provider                 (N5)
5  golden journey                        the full stack, one path          (N2)
6  build images                          not pushed
```

Cheapest first: a formatting error must not wait for containers.

Every step is **one command, runnable locally** (`N7`). A step that exists only in
CI is a step nobody can debug — and the failure that matters is always the one that
cannot be reproduced.

### Not in the gate

| Excluded | Why |
|---|---|
| Real-model tests | Cost, latency, non-determinism. Correctness must not depend on provider availability (`N4`) |
| Load tests | A measurement, not an assertion |
| Browser matrix | One browser for one journey. Cross-browser is a manual review before release |
| A story gallery build | It asserts nothing, and typecheck already covers the same files (`N11`) |
| Coverage and test-count floors | `N9`. The count floors rest on a premise measurement falsifies: no runner here reports zero tests with a success exit code |
| Generated-artefact staleness gates | One generator means there is nothing to detect divergence between |
| Architecture and cycle checks, documentation path linting | Machinery whose cost exceeded the confidence it added |

That last group deserves one sentence rather than a shrug: those checks were not
wrong in principle. They were **snapshots of a structure** — a module list, a cycle
baseline, a per-file line budget — and a redesign invalidates a snapshot on its
first commit. Their replacement is the invariant checklist
([testing.md](./testing.md) §13), which describes behaviour rather than shape.

## 3. Deploy

Manual or tag-triggered. **Never automatic on merge** — a solo operator chooses the
moment, and an automatic deploy on a red-adjacent commit is how a bad hour becomes a
bad day.

```text
1  resolve the image digests built by the PR pipeline
2  push them to the registry
3  on the host: pull those exact digests
4  run migrations to completion            ← BLOCKS
5  start the domain worker and scheduler, health-gate them
6  start the API, health-gate it
7  start web and the edge
8  smoke: the golden journey
9  on failure: the previous digest, up again
```

**Build once, promote by digest** (`N8`). Rebuilding at deploy means the artefact
tested is not the artefact deployed. A tag can be moved; a digest cannot — and "it
worked in CI" is only a useful sentence if the thing that ran in CI is the thing now
running.

**Migrations block** (`O4`). New containers do not take traffic against an
unmigrated schema, and the migration runs in the **new** image before anything
swaps, so a failure leaves the old containers untouched.

**Workers before the API** (step 5). Jobs are written by the API and consumed by a
worker; starting the API first opens a window where work is enqueued that nothing
can consume at the current schema version.

CI does not reach the host. Deployment is a host-side command, which means CI needs
no host credential — see §5.

The gate the deploy is conditioned on must be checked **explicitly**: a workflow
completion covers failure and cancellation too, so a gate that only asks "did the
test workflow finish" passes on red. And the commit checked out must be the commit
that was **tested**, not the branch tip at the time the deploy runs — otherwise the
artefact contains something no gate saw.

## 4. Versioning

```text
images       identity is the digest
release      a date-based tag
contracts    semantic versioning only where an external consumer exists
```

A version number is a contract with the consumer of a versioned artefact. Nothing
here has a consumer outside its own deployment, so a version number would be
ceremony. The one place it would mean something is a wire contract another
repository consumes — and the dictionary library's contract is that place, which is
why it is pinned to a commit rather than a range.

## 5. Secrets in CI

```text
registry credentials     for the push
```

That is the whole list.

**No production database URL. No signing secret. No provider key. No host access.**
CI does not need them, and a CI system holding them is a larger attack surface than
the deployment it serves — one with more contributors, more third-party actions, and
a log that is readable by anyone who can read the run.

This is also why the deploy is a host-side command: it is the design decision that
lets the secret list be one line.

## 6. Local parity

```text
the gate runs the same commands a developer runs
```

`N7`. Divergence between local and CI is how a green pipeline starts testing a
different system than the one being written.

Containers are what make this hold: the integration suite brings up its own
dependencies, so a clean clone runs it with no prior setup — and "unreachable
dependency" means a real fault rather than a missing local step (`N3`).

## 7. What the gate is for

Worth stating, because the previous pipeline had drifted into proving other things:

> **The gate answers one question: does the invariant checklist still hold?**

Not "is coverage above a number", not "does the structure match a baseline", not
"did every generated file get regenerated". Those are proxies, and each one had
found its own way to be green while the thing it stood for was broken.

## 8. Invariants for the checklist

CI's own, and the last two are the ones that were violated:

```text
every gate step is runnable locally with one command
the integration suite runs on a clean clone with no prior setup
a step that cannot reach its dependency FAILS rather than skipping
the deploy is conditioned on the test workflow's CONCLUSION, not its completion
the deployed artefact is the digest built from the commit that was tested
CI holds no host, database, signing, or provider credential
a red gate blocks the deploy
```
