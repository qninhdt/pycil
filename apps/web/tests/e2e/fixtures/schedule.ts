import { execFile } from "node:child_process"
import { promisify } from "node:util"

import { composeApiService, repoRoot } from "./env"

const run = promisify(execFile)

/**
 * Review schedule seeding — the one deliberate exception to the API-only rule.
 *
 * `fixtures/api.ts` builds everything through the same endpoints the browser uses,
 * on purpose: a fixture that writes rows directly can reach states the application
 * could never produce, and then the suite passes while the product is broken. That
 * rule holds everywhere else in this harness.
 *
 * It cannot hold here, and not for convenience. FSRS state is a function of
 * *elapsed time*: a sense is due because days passed, and mastery is high because
 * reviews succeeded across those days. There is deliberately no endpoint that sets
 * `next_review_date` or `mastery` — one would let a learner forge their own
 * progress, so its absence is a feature.
 *
 * Without this, a whole layer of the product is untestable:
 *
 * - `free_text` questions exist only at difficulty 3-4 (verified against
 *   `lexi.questions`), and those levels are only requested by
 *   `sample_requested_level` for a **due** sense with high mastery
 *   (`learning/policy.py`). A new sense always requests `ASSESSMENT_FLOOR = 1`
 *   (`learning/planning.py`), where only `single_choice` is generated.
 * - So the rubric-graded path — a worker grading an answer, the verdict arriving
 *   over SSE rather than in the response, a reload re-subscribing to an outstanding
 *   task — is unreachable from a deck of new words, despite being the only
 *   asynchronous path in the product and therefore the most fragile.
 *
 * Skipping that spec was the alternative, and it is worse than this exception: it
 * would report "not guaranteed in a short session" forever while never running
 * once, which is a coverage gap dressed as a pass.
 *
 * The blast radius is kept small on purpose: only `user_sense_stats` (the one table
 * that is purely a function of time), only for a learner this run just minted, with
 * every value bound as a parameter rather than interpolated.
 */

/**
 * Makes senses due for review, with mastery high enough to request levels 3-4.
 *
 * `mastery` defaults to 90, which lands in the top band (81-100) whose profile is
 * `{2: 0.10, 3: 0.50, 4: 0.40}`, so checkpoints request the levels where `free_text`
 * and `text_span` supply actually exists.
 *
 * `status` becomes `scheduled` rather than `new` because the planner's due query
 * selects on it: a past `next_review_date` on a `new` row is not a due candidate,
 * and the sense would be admitted for acquisition instead.
 */
export async function markSensesDue(
  userId: string,
  senseIds: number[],
  { mastery = 90, daysOverdue = 1 }: { mastery?: number; daysOverdue?: number } = {},
): Promise<void> {
  if (senseIds.length === 0) return

  // Coerced and validated here so nothing a caller supplies can reach SQL as
  // syntax; the statement itself binds every value.
  const ids = senseIds.map((id) => Number(id))
  if (!ids.every((id) => Number.isInteger(id))) {
    throw new Error(`markSensesDue needs integer sense ids, got: ${senseIds.join(", ")}`)
  }

  // Passed with `-e` rather than through this process's own environment. `compose
  // exec` does not forward the caller's variables into the container: setting them
  // on the `docker` process only configures the client, and the script then dies on
  // `KeyError` inside the container. Values still travel as environment entries
  // rather than being interpolated into the script, so nothing here reaches SQL as
  // syntax.
  const seedEnv = [
    ["E2E_SEED_UID", userId],
    ["E2E_SEED_IDS", ids.join(",")],
    ["E2E_SEED_MASTERY", String(mastery)],
    ["E2E_SEED_DAYS", String(daysOverdue)],
  ].flatMap(([key, value]) => ["-e", `${key}=${value}`])

  try {
    await run(
      "docker",
      [
        "compose",
        "exec",
        "-T",
        ...seedEnv,
        composeApiService,
        "python",
        "-c",
        SEED_SCRIPT,
      ],
      { cwd: repoRoot, maxBuffer: 1024 * 1024 },
    )
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    throw new Error(
      `Could not seed a review schedule for ${ids.length} sense(s).\n\n` +
        "This is what makes the returning-learner specs possible: free-text " +
        "questions exist only at difficulty 3-4, and those levels are requested " +
        "only for a due sense with high mastery.\n\n" +
        detail,
    )
  }
}

/**
 * Run inside the API container, through the application's own engine.
 *
 * Using SQLAlchemy rather than a `psql` binary means no extra tooling in the image
 * and proper parameter binding. Values arrive as environment variables, so the
 * script itself contains no interpolated data.
 */
const SEED_SCRIPT = [
  "import asyncio, os",
  "from sqlalchemy import text",
  "from pycil.db.session import engine",
  "",
  "uid = os.environ['E2E_SEED_UID']",
  "ids = [int(x) for x in os.environ['E2E_SEED_IDS'].split(',')]",
  "mastery = int(os.environ['E2E_SEED_MASTERY'])",
  "days = int(os.environ['E2E_SEED_DAYS'])",
  "",
  "SQL = text(",
  "    'INSERT INTO user_sense_stats ('",
  "    ' user_id, sense_id, stability, difficulty, mastery, interval_days,'",
  "    ' last_review_date, next_review_date, review_count, lapse_count, status'",
  "    ') VALUES ('",
  "    ' CAST(:uid AS uuid), :sid, 120.0, 5.0, :mastery, 30.0,'",
  "    \" NOW() - make_interval(days => :days + 30),\"",
  "    \" NOW() - make_interval(days => :days),\"",
  "    \" 6, 0, CAST('scheduled' AS sensestatus)\"",
  "    ')'",
  "    ' ON CONFLICT (user_id, sense_id) DO UPDATE SET'",
  "    ' mastery = EXCLUDED.mastery, stability = EXCLUDED.stability,'",
  "    ' interval_days = EXCLUDED.interval_days,'",
  "    ' last_review_date = EXCLUDED.last_review_date,'",
  "    ' next_review_date = EXCLUDED.next_review_date,'",
  "    ' review_count = EXCLUDED.review_count, status = EXCLUDED.status'",
  ")",
  "",
  "async def main():",
  "    async with engine.begin() as conn:",
  "        for sid in ids:",
  "            await conn.execute(",
  "                SQL,",
  "                {'uid': uid, 'sid': sid, 'mastery': mastery, 'days': days},",
  "            )",
  "",
  "asyncio.run(main())",
  "print('seeded', len(ids))",
].join("\n")
