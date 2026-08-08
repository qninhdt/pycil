#!/usr/bin/env python3
"""Extract the two Python-defined contracts the web client re-declares by hand.

Both are mirrored across a language boundary, and both TypeScript suites assert
against literals in their own repo — so neither can notice the Python side moving.
That is the class of problem `extract-error-codes.py` already solves here: a test
asserts what its fixture says, codegen asserts what the other language says.

1. Mastery bands (`pycil.policy.policy`). `LEVEL_PROFILES` + `STAGE_NAMES` are
   re-typed in `lib/design/mastery.ts`. Both render on the same screens — a deck row
   shows the server's `masteryStageName` while the dashboard and study verdict
   resolve the name locally — so drift shows one learner two labels for one score.

2. The grading result (`shared.realtime.payloads.GradingResult`). Its keys are read
   by string at `lib/study/grade-snapshot.ts`, and every read is defensive
   (`asNumber`/`asBoolean` -> null on mismatch). So renaming `grade_score` in Python
   produces a silently blank verdict: no exception, no type error, the unit suite
   still green, and a learner who just answered sees no score.

   The wire names come from `to_dict()`, NOT the field names — the dataclass is
   snake_case and the mapping is explicit in that method. Reading the field names
   would generate a contract nothing on the wire matches.

Run from the repo root (no configured Python env needed — this parses, never
imports):
    python3 scripts/extract-realtime-contracts.py

CI runs it and fails on a dirty tree afterwards, which turns "the generated file is
stale" from something nobody notices into a red build.
"""

from __future__ import annotations

import ast
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
POLICY = ROOT / "apps" / "api" / "pycil" / "policy" / "policy.py"
PAYLOADS = ROOT / "packages" / "shared-py" / "shared" / "realtime" / "payloads.py"
CHANNELS = ROOT / "packages" / "shared-py" / "shared" / "realtime" / "channels.py"
WEB_LIB = ROOT / "apps" / "web" / "lib"
MASTERY_OUT = WEB_LIB / "design" / "mastery.generated.ts"
GRADING_OUT = WEB_LIB / "realtime" / "grading-result.generated.ts"

# `float | None` -> a nullable number on the wire. Only the types GradingResult
# actually uses are mapped; anything else is a hard error rather than a guess,
# because silently emitting `unknown` would recreate the hole this closes.
_TS_TYPES = {
    "str": "string",
    "int": "number",
    "float": "number",
    "bool": "boolean",
    "dict": "Record<string, unknown>",
}


def _fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def _parse(path: pathlib.Path) -> ast.Module:
    if not path.exists():
        _fail(f"{path.relative_to(ROOT)} not found — did it move?")
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# --- mastery bands --------------------------------------------------------------


def mastery_bands() -> list[tuple[int, int, str]]:
    """`[(lo, hi, stage_name)]` in band order, read from the policy module.

    Both halves come from one file and are checked against each other here, the
    same way `policy.py` raises at import when the two lengths disagree. A
    generator that trusted one and not the other could emit five bands with four
    names.
    """
    tree = _parse(POLICY)
    bounds: list[tuple[int, int]] = []
    names: list[str] = []

    for node in tree.body:
        if not isinstance(node, ast.AnnAssign | ast.Assign):
            continue
        target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0]
        if not isinstance(target, ast.Name) or node.value is None:
            continue

        if target.id == "LEVEL_PROFILES" and isinstance(node.value, ast.Tuple):
            for element in node.value.elts:
                # `_Band(0, 10, {...})` — the two leading positional ints are the
                # inclusive bounds. The profile dict is deliberately not read: the
                # difficulty mix is server-side sampling policy and no browser
                # needs it.
                if not (isinstance(element, ast.Call) and len(element.args) >= 2):
                    continue
                lo, hi = element.args[0], element.args[1]
                if isinstance(lo, ast.Constant) and isinstance(hi, ast.Constant):
                    bounds.append((int(lo.value), int(hi.value)))

        elif target.id == "STAGE_NAMES" and isinstance(node.value, ast.Tuple):
            names = [
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            ]

    if not bounds:
        _fail("no LEVEL_PROFILES bands found in policy.py")
    if not names:
        _fail("no STAGE_NAMES found in policy.py")
    if len(bounds) != len(names):
        _fail(f"{len(names)} stage names for {len(bounds)} bands — policy.py is inconsistent")

    # The bands must tile 0..100 with no gap or overlap, because `masteryBand()`
    # falls back to the last band when its `find` misses. A gap would therefore
    # render as "Fluent" rather than as an error, so it is caught here instead.
    if bounds[0][0] != 0:
        _fail(f"bands start at {bounds[0][0]}, expected 0")
    if bounds[-1][1] != 100:
        _fail(f"bands end at {bounds[-1][1]}, expected 100")
    for (_, previous_hi), (lo, _) in zip(bounds[:-1], bounds[1:], strict=True):
        if lo != previous_hi + 1:
            _fail(f"bands are not contiguous: {previous_hi} is followed by {lo}")

    return [(lo, hi, name) for (lo, hi), name in zip(bounds, names, strict=True)]


def mastered_floor() -> int:
    """Read the server-owned statistics threshold from the policy module."""
    tree = _parse(POLICY)
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if (
            isinstance(target, ast.Name)
            and target.id == "MASTERED_FLOOR"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, int)
        ):
            return node.value.value
    _fail("MASTERED_FLOOR not found in policy.py")
    raise AssertionError("unreachable")  # pragma: no cover - _fail exits


# --- grading result -------------------------------------------------------------


def grading_fields() -> list[tuple[str, str, bool]]:
    """`[(wire_name, ts_type, nullable)]` for the grading payload.

    The wire names come from the `to_dict()` mapping and the types from the
    matching field annotations, so the two are joined here exactly as they are on
    the wire: alias for the key, annotation for the value.
    """
    tree = _parse(PAYLOADS)
    dataclass = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "GradingResult"
        ),
        None,
    )
    if dataclass is None:
        _fail("GradingResult not found in payloads.py")

    annotations: dict[str, tuple[str, bool]] = {}
    for statement in dataclass.body:
        if not isinstance(statement, ast.AnnAssign) or not isinstance(statement.target, ast.Name):
            continue
        annotations[statement.target.id] = _annotation_to_ts(
            statement.annotation, statement.target.id
        )

    to_dict = next(
        (
            node
            for node in dataclass.body
            if isinstance(node, ast.FunctionDef) and node.name == "to_dict"
        ),
        None,
    )
    if to_dict is None:
        _fail("GradingResult.to_dict not found — the wire names live there")

    mapping = next(
        (
            node.value
            for node in ast.walk(to_dict)
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)
        ),
        None,
    )
    if mapping is None:
        _fail("GradingResult.to_dict does not return a dict literal")

    fields: list[tuple[str, str, bool]] = []
    for key, value in zip(mapping.keys, mapping.values, strict=True):
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            _fail("to_dict has a non-literal key — the wire contract must be readable")
        # `"senseId": self.sense_id` — resolve the value back to the annotated field.
        if not (isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name)):
            _fail(f"to_dict entry {key.value!r} is not a plain field read")
        field = value.attr
        if field not in annotations:
            _fail(f"to_dict reads {field!r}, which is not an annotated field")
        ts_type, nullable = annotations[field]
        fields.append((key.value, ts_type, nullable))

    if not fields:
        _fail("GradingResult.to_dict produced no fields")
    return fields


def _annotation_to_ts(annotation: ast.expr, field: str) -> tuple[str, bool]:
    """`(ts_type, nullable)` for one annotation. Unknown types are an error."""
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        left, nullable_left = _annotation_to_ts(annotation.left, field)
        right, nullable_right = _annotation_to_ts(annotation.right, field)
        if right == "null":
            return left, True
        if left == "null":
            return right, True
        _fail(f"{field}: unions other than `X | None` are not supported ({left} | {right})")
    if isinstance(annotation, ast.Constant) and annotation.value is None:
        return "null", True
    if isinstance(annotation, ast.Name):
        if annotation.id not in _TS_TYPES:
            _fail(f"{field}: no TypeScript mapping for {annotation.id!r}")
        return _TS_TYPES[annotation.id], False
    _fail(f"{field}: unsupported annotation {ast.dump(annotation)}")
    raise AssertionError("unreachable")  # pragma: no cover - _fail exits


# --- channel prefix -------------------------------------------------------------


def channel_namespace() -> str:
    """The `async` in `async:{task_id}`, so the client builds the same channel."""
    tree = _parse(CHANNELS)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if (
                isinstance(target, ast.Name)
                and target.id == "_ASYNC_NS"
                and isinstance(node.value, ast.Constant)
            ):
                return str(node.value.value)
    _fail("_ASYNC_NS not found in channels.py")
    raise AssertionError("unreachable")  # pragma: no cover - _fail exits


# --- rendering ------------------------------------------------------------------


def source_fingerprint() -> str:
    """Stable identity for the three Python inputs this generator reads.

    A Git ``HEAD`` changes when the generated files themselves are committed,
    which would make the CI freshness check fail after every commit. Hash the
    inputs instead: the provenance still changes when a contract changes, while
    regeneration remains deterministic across checkout and commit boundaries.
    """
    digest = hashlib.sha256()
    for source in (POLICY, PAYLOADS, CHANNELS):
        digest.update(source.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(source.read_bytes())
    return digest.hexdigest()[:12]


_REGENERATE = "python3 scripts/extract-realtime-contracts.py"


def _header(source: str, purpose: list[str]) -> list[str]:
    return [
        "/**",
        f" * Generated from {source} by scripts/extract-realtime-contracts.py. Do not edit.",
        " *",
        f" * Source fingerprint: {source_fingerprint()}",
        " *",
        *(f" * {line}".rstrip() for line in purpose),
        " *",
        f" * Regenerate with:  {_REGENERATE}",
        " */",
        "",
    ]


def render_mastery(bands: list[tuple[int, int, str]], floor: int) -> str:
    stages = " | ".join(str(index) for index in range(1, len(bands) + 1))
    lines = [
        *_header(
            "apps/api/pycil/policy/policy.py",
            [
                "The mastery bands and their learner-visible names.",
                "",
                "Bounds are inclusive on both ends and tile 0..100 with no gap, which the",
                "generator verifies before writing: `masteryBand()` falls back to the last",
                "band when its lookup misses, so a gap would silently render as the top",
                "stage rather than as an error.",
                "",
                "The band-resolving functions live in `mastery.ts` and stay hand-written.",
                "The numbers are the cross-language contract; the lookup logic is not.",
            ],
        ),
        f"export type MasteryStage = {stages}",
        "",
        "export interface MasteryBand {",
        "  stage: MasteryStage",
        "  name: string",
        "  /** Inclusive lower bound of the mastery score. */",
        "  min: number",
        "  /** Inclusive upper bound of the mastery score. */",
        "  max: number",
        "}",
        "",
        "export const MASTERY_BANDS: readonly MasteryBand[] = [",
    ]
    for index, (lo, hi, name) in enumerate(bands, start=1):
        lines.append(f'  {{ stage: {index}, name: "{name}", min: {lo}, max: {hi} }},')
    lines += [
        "] as const",
        "",
        "/**",
        " * The server-owned score at or above which a sense counts as mastered.",
        " *",
        " * Read from `MASTERED_FLOOR` in the policy module. This is intentionally",
        " * separate from the visual bands: the approved floor is 80 while Fluent",
        " * begins at 81.",
        " */",
        f"export const MASTERED_FLOOR = {floor}",
        "",
    ]
    return "\n".join(lines)


def render_grading(fields: list[tuple[str, str, bool]], namespace: str) -> str:
    lines = [
        *_header(
            "packages/shared-py/shared/realtime/payloads.py",
            [
                "The inner `result` payload of a settled grading task.",
                "",
                "`task-snapshot.ts` validates the envelope around this properly and then",
                "stops at `Record<string, unknown>`, so every field below used to be read",
                "by bare string key. Those reads are defensive — a mismatch becomes null,",
                "not a throw — which means renaming a field on the Python side produced a",
                "blank verdict for a learner who had just answered, with nothing red",
                "anywhere to say so.",
                "",
                "Field names are the wire names from `GradingResult.to_dict()`, not the",
                "dataclass attributes: the class is snake_case and that method is where",
                "the camelCase mapping is stated.",
            ],
        ),
        "export interface GradingResultPayload {",
    ]
    for name, ts_type, nullable in fields:
        suffix = " | null" if nullable else ""
        lines.append(f"  {name}: {ts_type}{suffix}")
    lines += [
        "}",
        "",
        "/** Every key the payload carries, in wire order. */",
        "export const GRADING_RESULT_KEYS = [",
        *(f'  "{name}",' for name, _, _ in fields),
        "] as const",
        "",
        "/**",
        " * Whether a value is a usable grading result.",
        " *",
        " * Checks the fields the verdict is actually built from and tolerates extra",
        " * keys, so adding a field to the Python payload cannot reject a snapshot a",
        " * client already understands. A *renamed* field does fail here, which is the",
        " * whole point.",
        " */",
        "export function isGradingResultPayload(",
        "  value: unknown,",
        "): value is GradingResultPayload {",
        '  if (!value || typeof value !== "object") return false',
        "  const payload = value as Record<string, unknown>",
        "  return (",
    ]
    checks: list[str] = []
    for name, ts_type, nullable in fields:
        if ts_type == "Record<string, unknown>":
            check = f'(payload.{name} === null || typeof payload.{name} === "object")'
        elif nullable:
            check = f'(payload.{name} === null || typeof payload.{name} === "{ts_type}")'
        else:
            check = f'typeof payload.{name} === "{ts_type}"'
        checks.append(check)
    for index, check in enumerate(checks):
        tail = "" if index == len(checks) - 1 else " &&"
        lines.append(f"    {check}{tail}")
    lines += [
        "  )",
        "}",
        "",
        "/**",
        " * The channel namespace a durable task is published on.",
        " *",
        " * Emitted so the subscriber builds the same channel the publisher does. Low",
        " * risk today because authorization never parses ownership out of a channel",
        " * name — the subscribe proxy looks up the interest row and fails closed — but",
        " * a mismatch means every event lands somewhere no client is listening.",
        " */",
        f'export const ASYNC_TASK_NAMESPACE = "{namespace}"',
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    bands = mastery_bands()
    floor = mastered_floor()
    fields = grading_fields()
    namespace = channel_namespace()

    MASTERY_OUT.write_text(render_mastery(bands, floor), encoding="utf-8")
    GRADING_OUT.write_text(render_grading(fields, namespace), encoding="utf-8")

    print(f"wrote {len(bands)} mastery bands to {MASTERY_OUT.relative_to(ROOT)}")
    print(f"wrote {len(fields)} grading fields to {GRADING_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
