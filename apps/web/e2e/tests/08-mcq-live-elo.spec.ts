/**
 * Spec 08 (LIVE): real MCQ generation → answer → DB ELO mutation.
 *
 * The seed enriches a term but plants NO question, so the first next_question
 * fires real generation (pending→ready; the client auto-polls on "pending" via
 * pollIntervalForStatus). Under the stub profile the worker returns the canned
 * MCQData fixture; under the live profile it calls real OpenRouter. Either way a
 * questions row appears and the learn loop serves it.
 *
 * The learn loop commits ELO to user_term_stats only after 2 correct
 * first-attempts (_REQUIRED_CORRECT_FIRSTS), so the spec must answer CORRECTLY
 * twice. It cannot know the correct option ahead of time (LLM-generated), so it
 * reads correct_index → options[correct_index] back from the generated row and
 * clicks that text. Structural assertion: the ELO row moved consistent with a
 * correct verdict (perfect run from 1000 → strictly up). Never asserts exact
 * question text.
 *
 * Worker-gated: needs a worker to generate, so it runs in local staging +
 * nightly, not the per-PR CI e2e job. Set E2E_WORKER_SPECS=true to enable it.
 */
import { test, expect } from "../fixtures/auth";
import {
  seedLiveLearnDeck,
  readQuestionForDefinition,
  readUserTermStats,
  type LiveLearnSeed,
} from "../fixtures/db-seed";

const GEN_DEADLINE_MS = 120_000;
const POLL_INTERVAL_MS = 2_000;
const RUN_WORKER_SPECS = process.env["E2E_WORKER_SPECS"] === "true";

let seeded: LiveLearnSeed;

test.beforeAll(() => {
  if (!RUN_WORKER_SPECS) return;
  seeded = seedLiveLearnDeck();
});

test.describe("08 live MCQ generation → ELO mutation", () => {
  test.skip(!RUN_WORKER_SPECS, "requires pycil worker; excluded from per-PR CI");

  test.setTimeout(GEN_DEADLINE_MS + 90_000);

  test("a live-generated MCQ is answered and mutates ELO in the DB", async ({
    authenticatedPage,
  }) => {
    const before = readUserTermStats(seeded.userId, seeded.definitionId);
    expect(before, "seed guarantees a baseline user_term_stats row").not.toBeNull();

    const page = await authenticatedPage();
    await page.goto(`/decks/${seeded.deckId}/learn`);

    // Pre-session gate: theme picker → Start session begins round 0, which
    // triggers the first next_question → live generation.
    const startBtn = page.getByRole("button", { name: /start session/i });
    await expect(startBtn).toBeVisible({ timeout: 20_000 });
    await startBtn.click();

    // Poll the DB until the worker inserts the generated MCQ, then read its
    // correct option text back (we can't predict LLM content).
    await expect
      .poll(() => readQuestionForDefinition(seeded.definitionId)?.id ?? null, {
        message: "worker generated a question row",
        timeout: GEN_DEADLINE_MS,
        intervals: [POLL_INTERVAL_MS],
      })
      .not.toBeNull();
    const q = readQuestionForDefinition(seeded.definitionId);
    expect(q, "worker generated a question row").not.toBeNull();
    expect(q!.type, "generated question is an MCQ").toBe("MULTIPLE_CHOICE");
    expect(q!.correctOption, "MCQ exposes a correct option").not.toBeNull();

    const correct = q!.correctOption as string;

    // Round 1: the client auto-polls "pending" and renders the MCQ once ready.
    // Click the correct option (its text == correct).
    const opt1 = page.getByRole("button", { name: correct, exact: true });
    await expect(opt1).toBeVisible({ timeout: GEN_DEADLINE_MS });
    await opt1.click();
    await expect(page.getByText("✓ Correct")).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: /continue|complete session/i }).click();

    // Round 2: same term resurfaces (correct_firsts 1 → needs 2). A second
    // correct first-attempt commits ELO and completes the session.
    const opt2 = page.getByRole("button", { name: correct, exact: true });
    await expect(opt2).toBeVisible({ timeout: 20_000 });
    await opt2.click();
    await expect(page.getByText("Session Complete")).toBeVisible({ timeout: 20_000 });

    // BE→DB proof: ELO commit ran. Perfect 2/2 from baseline 1000 → score up,
    // review_count incremented. This is the side effect the smoke specs skip.
    const after = readUserTermStats(seeded.userId, seeded.definitionId);
    expect(after, "stats row still present").not.toBeNull();
    expect(after!.masteryScore, "ELO moved up on a perfect run").toBeGreaterThan(
      before!.masteryScore,
    );
    expect(after!.reviewCount, "review recorded").toBeGreaterThan(before!.reviewCount);
  });
});
