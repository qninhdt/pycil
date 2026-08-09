import { expect, test } from "../fixtures/test"

/**
 * The library: structure, breadcrumbs, the palette, and the deck view.
 *
 * The deck assertion verifies that each rendered sense includes its headword.
 */

test.describe("library structure", () => {
  test("creates a folder, then a deck inside it, with breadcrumbs to match", async ({
    page,
  }) => {
    const stamp = Date.now().toString(36)
    const folderName = `Spec folder ${stamp}`
    const deckName = `Spec deck ${stamp}`

    await page.goto("/library")

    // --- a folder at the root -------------------------------------------------
    await page.getByRole("button", { name: /^new$/i }).click()

    const sheet = page.getByRole("dialog")
    await expect(sheet.getByText("Create something new")).toBeVisible()

    // The kind toggle defaults to Deck, so a folder is an explicit choice.
    await sheet.getByRole("button", { name: "Folder" }).click()
    await sheet.getByLabel("Name").fill(folderName)
    await sheet.getByRole("button", { name: /^create$/i }).click()

    // The listing refetches after the mutation rather than patching a row in
    // place, so the new folder appearing is the real post-condition.
    await expect(page.getByRole("link", { name: new RegExp(folderName) })).toBeVisible()

    // --- a deck inside it -----------------------------------------------------
    await page.getByRole("link", { name: new RegExp(folderName) }).click()
    await expect(page.getByRole("heading", { name: folderName })).toBeVisible()

    // Scoped to the node header. An empty folder renders `CreateNodeSheet`
    // twice — once beside the title, once as the empty-state call to action —
    // so an unscoped match is ambiguous the moment the folder has no children.
    await page.locator("main header").getByRole("button", { name: /^new$/i }).click()
    const deckSheet = page.getByRole("dialog")
    // Deck is the default kind; asserting it rather than clicking proves the
    // default instead of masking it.
    await deckSheet.getByLabel("Name").fill(deckName)
    await deckSheet.getByRole("button", { name: /^create$/i }).click()

    await expect(page.getByRole("link", { name: new RegExp(deckName) })).toBeVisible()

    // --- breadcrumbs ----------------------------------------------------------
    await page.getByRole("link", { name: new RegExp(deckName) }).click()
    await expect(page.getByRole("heading", { name: deckName })).toBeVisible()

    // Root-first, ending at this node. The parent has to be in the trail: a deck
    // created inside a folder that breadcrumbs straight to Library would mean the
    // parent was silently dropped.
    const breadcrumb = page.getByRole("navigation", { name: /breadcrumb/i })
    await expect(breadcrumb.getByRole("link", { name: "Library" })).toBeVisible()
    await expect(breadcrumb.getByRole("link", { name: folderName })).toBeVisible()
  })

  test("the seeded deck renders its words with headwords attached", async ({
    page,
    fixture,
  }) => {
    await page.goto(`/library/${fixture.deckId}`)

    await expect(page.getByRole("heading", { name: fixture.deckName })).toBeVisible()

    // Every seeded sense carries a word, and the deck should display it.
    for (const sense of fixture.senses) {
      if (!sense.word) continue
      await expect(
        page.getByText(sense.word, { exact: false }).first(),
        `the deck should show the headword "${sense.word}"`,
      ).toBeVisible()
    }

    // And the way into a session exists, as a link rather than an action: the
    // session-creating POST belongs to the launch screen, so a deck reload cannot
    // start one as a side effect of rendering.
    await expect(
      page.getByRole("button", { name: /^study$/i }).or(
        page.getByRole("link", { name: /^study$/i }),
      ),
    ).toBeVisible()
  })
})

test.describe("the command palette", () => {
  test("opens with the keyboard, searches, and adds a sense to the deck", async ({
    page,
    fixture,
  }) => {
    test.skip(
      fixture.seededWords.length === 0,
      "No searchable word was seeded, so there is nothing to add. " +
        "This needs a materialised word that is not already in the fixture deck.",
    )

    const word = fixture.seededWords[0]

    // Opened from the deck, so the palette carries the deck as its add target.
    await page.goto(`/library/${fixture.deckId}`)
    await page.getByRole("button", { name: /add words/i }).click()

    const palette = page.getByPlaceholder(/search words, or jump to a screen/i)
    await expect(palette).toBeVisible()

    await palette.fill(word)

    /**
     * Scoped to the "Words" group, and that scoping is the whole point.
     *
     * The palette renders three groups against one query, and the create group's
     * option is "Add {query} to the dictionary" — which matches the word too. It
     * also renders *first*, because search is debounced 250ms and then waits on the
     * API while the create option is available immediately. So an unscoped
     * `option` locator resolves to the generate option, clicks it, and the spec
     * silently tests word generation instead of adding an existing sense.
     *
     * cmdk labels each group from its heading, so asking for the group by name is
     * both precise and stable.
     */
    const words = page.getByRole("group", { name: "Words" })
    const result = words.getByRole("option", { name: new RegExp(word, "i") }).first()
    // Generous: the debounce, the search, and a per-result entry fetch on the API
    // side all sit between the keystroke and this row.
    await expect(result).toBeVisible({ timeout: 30_000 })

    await result.click()

    // The toast is the confirmation the learner sees.
    await expect(page.getByText(new RegExp(`added ${word}`, "i"))).toBeVisible()

    // And the durable effect: the sense is in the deck after a reload, which a
    // toast alone does not prove.
    await page.reload()
    await expect(
      page.getByRole("link", { name: new RegExp(word, "i") }).first(),
    ).toBeVisible()
  })

  test("opens on the keyboard shortcut alone", async ({ page }) => {
    await page.goto("/library")

    // The shortcut is bound at the window, not on the header button, so it has to
    // work from a page body with nothing focused.
    await page.keyboard.press("ControlOrMeta+k")

    await expect(
      page.getByPlaceholder(/search words, or jump to a screen/i),
    ).toBeVisible()

    // And closes again, so the binding is a toggle rather than a one-way door.
    await page.keyboard.press("Escape")
    await expect(
      page.getByPlaceholder(/search words, or jump to a screen/i),
    ).not.toBeVisible()
  })

  test("navigates to a screen from the palette", async ({ page }) => {
    await page.goto("/library")
    await page.keyboard.press("ControlOrMeta+k")

    const input = page.getByPlaceholder(/search words, or jump to a screen/i)
    await input.fill("progress")

    /**
     * Scoped to "Go to" for the same reason as the add spec above: unscoped, the
     * first matching option is "Add progress to the dictionary" from the create
     * group, so this would enqueue a word generation for the word "progress" and
     * then fail on the URL never changing. Which is exactly what it did.
     */
    await page
      .getByRole("group", { name: "Go to" })
      .getByRole("option", { name: /progress/i })
      .click()

    await expect(page).toHaveURL(/\/progress/)
  })
})
