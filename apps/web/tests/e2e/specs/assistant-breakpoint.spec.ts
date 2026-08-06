import type { Page } from "@playwright/test"

import { expect, test } from "../fixtures/test"

/**
 * The assistant conversation survives the width that swaps its two renderings.
 *
 * The drawer and the sidebar are separate components for a real reason — a portal
 * cannot sit in the layout flow, so neither can be the other with CSS — and they are
 * mutually exclusive by viewport. That makes 1024px an *unmount boundary*: crossing
 * it destroys one component and builds the other. Anything the destroyed one owned
 * in React state goes with it.
 *
 * Which is what a learner hit by rotating a tablet, dragging a window wider, or
 * opening devtools: the open conversation closed itself, the transcript emptied, and
 * the message held for "Send again" was gone. No error, nothing to recover from, and
 * invisible to every spec in the suite because they all run at one width.
 *
 * So this spec crosses the boundary in both directions and asserts the conversation
 * is still there. It deliberately asserts on what the learner sees rather than on
 * where the state lives: a future refactor may move it again, and this should still
 * be the thing that has to keep holding.
 */

/** Either side of the shell's `lg`, which is where the two renderings swap. */
const NARROW = { width: 390, height: 844 }
const WIDE = { width: 1440, height: 900 }

/**
 * Opens the assistant and creates a conversation to lose.
 *
 * Returns its title, which is the handle everything below is asserted through: it is
 * rendered by `ThreadList` at both widths, so one locator works either side of the
 * boundary.
 */
async function openConversation(page: Page): Promise<string | null> {
  await page.goto("/")

  const trigger = page.getByRole("button", { name: "Assistant" })
  // Absent rather than disabled when the deployment has no assistant, so its absence
  // is a skip rather than a failure.
  if (!(await trigger.isVisible().catch(() => false))) return null
  await trigger.click()

  const create = page.getByRole("button", { name: /new conversation/i })
  await expect(create).toBeVisible()
  await create.click()

  // Creating opens it, so the transcript area is what proves the click landed rather
  // than the row merely appearing in the list.
  const composer = page.getByRole("textbox")
  await expect(composer.first()).toBeVisible({ timeout: 30_000 })

  // The thread's own row, which `ThreadList` marks with `aria-current` while open.
  const openRow = page.locator("[aria-current='true']")
  await expect(openRow).toBeVisible()
  return (await openRow.innerText()).trim()
}

test.describe("the assistant across the breakpoint", () => {
  test("keeps the open conversation when the viewport crosses 1024px", async ({
    learnerPage,
  }) => {
    await learnerPage.setViewportSize(WIDE)
    const title = await openConversation(learnerPage)
    test.skip(title === null, "This deployment has no assistant.")

    // Wide to narrow: the sidebar unmounts and the drawer mounts. Before the state
    // was lifted, this is where `threadId` went back to null and the learner was
    // returned to the thread list with their conversation closed.
    await learnerPage.setViewportSize(NARROW)

    await expect(
      learnerPage.locator("[aria-current='true']"),
      "crossing to the narrow rendering closed the open conversation",
    ).toHaveText(new RegExp(escapeForRegExp(title!)))

    // And back, which unmounts the drawer and rebuilds the sidebar.
    await learnerPage.setViewportSize(WIDE)

    await expect(
      learnerPage.locator("[aria-current='true']"),
      "crossing back to the wide rendering closed the open conversation",
    ).toHaveText(new RegExp(escapeForRegExp(title!)))
  })

  test("keeps the draft's sent copy so a resend is still possible", async ({
    learnerPage,
  }) => {
    await learnerPage.setViewportSize(WIDE)
    const title = await openConversation(learnerPage)
    test.skip(title === null, "This deployment has no assistant.")

    // The composer clears its draft on submit, so the *only* copy of a sent message
    // is the one the surface holds. Losing it across the boundary turns "Send again"
    // into "retype the paragraph you just lost", which for the messages this
    // assistant takes is not a recovery at all.
    const composer = learnerPage.getByRole("textbox").first()
    await composer.fill("Add three words about weather to my deck")
    await composer.press("Enter")

    // Whatever the run does — stream, refuse on capacity, drop — the turn was sent,
    // which is the only precondition the held copy has.
    await expect(composer).toHaveValue("", { timeout: 30_000 })

    await learnerPage.setViewportSize(NARROW)

    // The conversation is still open, which is the precondition for the composer and
    // any retry affordance existing at all on the other side.
    await expect(
      learnerPage.locator("[aria-current='true']"),
      "the conversation closed, so nothing that depends on it could have survived",
    ).toHaveText(new RegExp(escapeForRegExp(title!)))

    // The learner's own words are still on screen: `buildTranscript` renders the
    // `user_message` event, and those events are what the unmount used to discard.
    await expect(
      learnerPage.getByText("Add three words about weather to my deck"),
      "the transcript emptied when the rendering swapped",
    ).toBeVisible()
  })
})

function escapeForRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}
