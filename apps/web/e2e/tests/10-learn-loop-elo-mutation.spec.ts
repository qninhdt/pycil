/**
 * Spec 10: Full learn-loop acceptance — UI answer → BE grade → DB ELO mutation.
 *
 * This is the real QA-tester flow the smoke specs (01-06) skip: it drives the
 * MCQ end-to-end and proves the side effects landed in Postgres.
 *
 * The seed plants ONE term + ONE deterministic MCQ (correct_index 0 →
 * "ephemeral"). learning_service commits ELO to user_term_stats only after
 * 2 correct-first answers (_REQUIRED_CORRECT_FIRSTS). With a single-term deck:
 *   round 0: answer correct → correct_firsts=1, round_complete (queue empties),
 *            session NOT complete → "✓ Correct" + "Continue".
 *   round 1: same term resurfaces; answer correct → correct_firsts=2 → ELO
 *            commits + session_complete → component jumps straight to the
 *            SessionComplete summary (early return, no footer for this answer).
 *
 * Acceptance assertions (not "page loads"):
 *   1. The known-correct option renders and is clickable.
 *   2. After the 1st submit, the UI shows "✓ Correct" + a Continue control.
 *   3. After the 2nd correct first-attempt, the session-complete screen renders.
 *   4. user_term_stats.mastery_score changed from the pre-session baseline
 *      (proves the BE ELO commit wrote to Postgres). A perfect 2/2 from ELO
 *      1000 yields a positive delta, so the score strictly increases.
 */
import { test, expect } from "../fixtures/auth";
import { seedDatabase, readUserTermStats, type SeededData } from "../fixtures/db-seed";

let seeded: SeededData;

test.beforeAll(() => {
  seeded = seedDatabase();
});

test.describe("10 learn loop → ELO mutation", () => {
  test("two correct first-attempts commit ELO to user_term_stats", async ({
    authenticatedPage,
  }) => {
    const before = readUserTermStats(seeded.userId, seeded.definitionId);
    // Seed guarantees a baseline row (mastery_score 1000, review_count 0).
    expect(before).not.toBeNull();

    const page = await authenticatedPage();
    await page.goto(`/decks/${seeded.deckId}/learn`);

    // Pre-session gate: the learn page opens on a theme picker, not the MCQ.
    // Click "Start session" to actually begin the round (POST /decks/{id}/learn).
    const startBtn = page.getByRole("button", { name: /start session/i });
    await expect(startBtn).toBeVisible({ timeout: 20_000 });
    await startBtn.click();

    // The correct option text is the term itself (seed MCQ correct_index 0).
    // Round 1: answer correctly. Wait for the MCQ to render first.
    const correctOption = page.getByRole("button", { name: /ephemeral/i });
    await expect(correctOption).toBeVisible({ timeout: 20_000 });
    await correctOption.click();

    // BE→FE: result state shows after grading; round completes (queue empties).
    await expect(page.getByText("✓ Correct")).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: /continue|complete session/i }).click();

    // Round 2: same term resurfaces (correct_firsts 1 → needs 2). Answering
    // correctly commits ELO and completes the session, so the component returns
    // the summary immediately — assert on that, not on a 2nd footer.
    const correctOption2 = page.getByRole("button", { name: /ephemeral/i });
    await expect(correctOption2).toBeVisible({ timeout: 20_000 });
    await correctOption2.click();

    await expect(page.getByText("Session Complete")).toBeVisible({ timeout: 15_000 });

    // BE→DB proof: the ELO commit ran. Perfect 2/2 from baseline 1000 → score up.
    const after = readUserTermStats(seeded.userId, seeded.definitionId);
    expect(after).not.toBeNull();
    expect(after!.masteryScore).toBeGreaterThan(before!.masteryScore);
  });
});
