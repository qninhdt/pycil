#!/usr/bin/env python3
"""Foreign-key delete rules, asserted against a schema Alembic actually built.

This exists because the test suite cannot see them. `tests/conftest.py` builds the
schema with `target_metadata.create_all()` from the ORM, never by running Alembic,
so a delete rule that differs between a migration and the model is invisible to
every test — including the account-deletion test, which passes because
`create_all` gives it whatever the ORM declares.

**`NO ACTION` is this codebase's deliberate default, not an oversight.**
`account_lifecycle/service.py:95-97` states the reasoning: deletion order is
hand-maintained in Python, and `NO ACTION` means a forgotten table *aborts the
deletion* rather than silently cascading — "which is exactly what surfaced the four
missing statements here". A cascade on a table nobody remembered is how learner
data disappears without a trace.

So this script does not demand `ondelete=`. It pins the rules that exist, so a
migration that quietly turns one into `CASCADE` — removing the loud failure that
design depends on — fails here instead of the first time an account is deleted.

Run against a database migrated to head.

Usage:
    extract-fk-delete-rules.py <sync-dsn>          # check against the baseline
    extract-fk-delete-rules.py <sync-dsn> --write  # record the current rules
"""

from __future__ import annotations

import json
import pathlib
import sys

BASELINE = pathlib.Path(__file__).with_name("fk-delete-rules-baseline.json")

QUERY = """
SELECT
    tc.table_name || '.' || tc.constraint_name AS constraint_id,
    ccu.table_name AS referenced_table,
    rc.delete_rule
FROM information_schema.table_constraints AS tc
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
   AND ccu.constraint_schema = tc.constraint_schema
JOIN information_schema.referential_constraints AS rc
    ON rc.constraint_name = tc.constraint_name
   AND rc.constraint_schema = tc.constraint_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public'
ORDER BY constraint_id
"""


def read_rules(dsn: str) -> dict[str, dict[str, str]]:
    import psycopg

    with psycopg.connect(dsn) as connection:
        rows = connection.execute(QUERY).fetchall()
    return {
        constraint_id: {"references": referenced, "delete_rule": rule}
        for constraint_id, referenced, rule in rows
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    dsn = sys.argv[1]
    write = "--write" in sys.argv[2:]

    rules = read_rules(dsn)
    if not rules:
        # An empty result means the database was never migrated, which would make
        # this check pass while asserting nothing.
        print("no foreign keys found — was the database migrated to head?", file=sys.stderr)
        return 1

    if write:
        BASELINE.write_text(json.dumps(rules, indent=2, sort_keys=True) + "\n")
        print(f"recorded {len(rules)} foreign keys to {BASELINE.name}")
        return 0

    if not BASELINE.exists():
        print(f"no baseline at {BASELINE}; run with --write to record one", file=sys.stderr)
        return 1

    expected: dict[str, dict[str, str]] = json.loads(BASELINE.read_text())

    changed = [
        (key, expected[key]["delete_rule"], rules[key]["delete_rule"])
        for key in sorted(set(expected) & set(rules))
        if expected[key]["delete_rule"] != rules[key]["delete_rule"]
    ]
    added = sorted(set(rules) - set(expected))
    removed = sorted(set(expected) - set(rules))

    print(f"{len(rules)} foreign keys checked against the recorded baseline")

    if changed:
        print("\na delete rule changed:", file=sys.stderr)
        for key, was, now in changed:
            print(f"  {key}: {was} -> {now}", file=sys.stderr)
        print(
            "\nIf deliberate, re-record with --write and say in the commit why the "
            "new rule is right. Turning a NO ACTION into CASCADE removes the loud "
            "failure that account deletion's hand-maintained order depends on "
            "(`account_lifecycle/service.py:95-97`); turning a CASCADE into NO "
            "ACTION makes a deletion path abort that used to work.",
            file=sys.stderr,
        )
        return 1

    if added:
        print("\na new foreign key appeared:", file=sys.stderr)
        for key in added:
            print(f"  {key} -> {rules[key]['references']} ({rules[key]['delete_rule']})", file=sys.stderr)
        print(
            "\nIf it references `users`, account deletion must delete from that "
            "table explicitly — `NO ACTION` aborts the whole deletion otherwise. "
            "Add the statement to `account_lifecycle/service.py`, confirm the "
            "account-deletion test still passes, then re-record with --write.",
            file=sys.stderr,
        )
        return 1

    if removed:
        print("\na foreign key in the baseline no longer exists:", file=sys.stderr)
        for key in removed:
            print(f"  {key}", file=sys.stderr)
        print("\nRe-record with --write if the table or column was dropped.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
