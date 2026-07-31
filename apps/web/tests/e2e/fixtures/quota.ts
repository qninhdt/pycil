import { execFile } from "node:child_process"
import { promisify } from "node:util"

import { composeRedisService, redisPassword, repoRoot } from "./env"

const run = promisify(execFile)

/**
 * Grading-quota seeding, the second deliberate exception to the API-only rule.
 *
 * The budget is a Redis counter, not a row: `take_grading_slot`
 * (`learning/session_store.py`) does `INCR session:grading-quota:{uid}` with a 300s
 * expiry and refuses the 21st call in that window. Only rubric-graded formats reach
 * it — a rule-graded answer is scored in-request and never takes a slot.
 *
 * Reaching it honestly would mean submitting twenty free-text answers, each one a
 * live model grade. That is minutes of judge latency to observe a branch that turns
 * on a single integer, and it would exhaust the same budget every other spec in the
 * run depends on. So the counter is set directly to one below its limit and the spec
 * spends the last slot through the real UI.
 *
 * What is *not* faked is the interesting half. The rejection comes from the API's own
 * guard, the code travels the real wire, and the reducer, the notice, and the
 * following `/next` all run untouched. Only the twenty prior answers are elided, and
 * they prove nothing this spec is about.
 */

/**
 * Leaves exactly `remaining` grading slots in the learner's window.
 *
 * `remaining: 1` is the useful case: the next rubric-graded answer succeeds and the
 * one after it is refused, so a spec can assert both sides of the boundary against
 * one seeded state.
 *
 * The TTL is set explicitly. `take_grading_slot` only calls `EXPIRE` when its own
 * `INCR` returns 1, so a key written here without one would never expire and would
 * poison every later run against this Redis.
 */
export async function setGradingQuotaUsed(
  userId: string,
  { limit = 20, remaining = 1 }: { limit?: number; remaining?: number } = {},
): Promise<void> {
  const used = limit - remaining
  if (!Number.isInteger(used) || used < 0) {
    throw new Error(
      `setGradingQuotaUsed needs remaining (${remaining}) <= limit (${limit}).`,
    )
  }

  // `redis-cli` is in the official image, so this needs no extra tooling. The key
  // and value are separate argv entries rather than a shell string, so neither can
  // be read as command syntax.
  await redisCli(["SET", `session:grading-quota:${userId}`, String(used), "EX", "300"])
}

/** Clears the counter, so a spec that seeded it cannot leak into the next one. */
export async function clearGradingQuota(userId: string): Promise<void> {
  await redisCli(["DEL", `session:grading-quota:${userId}`])
}

async function redisCli(args: string[]): Promise<string> {
  try {
    const { stdout } = await run(
      "docker",
      [
        "compose",
        "exec",
        "-T",
        composeRedisService,
        "redis-cli",
        "-a",
        redisPassword(),
        // Without this the password warning is written to stderr on every call,
        // which turns a successful command into noise a reader has to dismiss.
        "--no-auth-warning",
        ...args,
      ],
      { cwd: repoRoot, maxBuffer: 1024 * 1024 },
    )
    return stdout.trim()
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    throw new Error(
      `redis-cli ${args[0]} failed against the "${composeRedisService}" service.\n\n` +
        "The grading quota lives in Redis, so this is how a spec reaches the " +
        "boundary without spending twenty live model grades.\n\n" +
        detail,
    )
  }
}
