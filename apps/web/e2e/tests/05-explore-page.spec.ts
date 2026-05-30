/**
 * Spec 05: Explore page — authenticated user can browse public decks.
 */
import { test } from "../fixtures/auth";
import { ExplorePage } from "../pages/explore-page";

test.describe("05 explore public decks", () => {
  test("explore page loads for authenticated user", async ({
    authenticatedPage,
  }) => {
    const page = await authenticatedPage();
    const explore = new ExplorePage(page);
    await explore.goto();
    await explore.expectLoaded();
  });
});
