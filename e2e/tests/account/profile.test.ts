import { test, expect } from "../../fixtures/index.ts";
import { Api, type Account } from "../../support/api.ts";

test("profile changes survive reload and the old handle is no longer public", async ({
  user,
}) => {
  const { page, account, api } = user;
  const handle = `learner_${user.subject.slice(-10).toLowerCase()}`;
  await page.goto(`/u/${account.id}`);
  await page.getByRole("button", { name: "Edit profile", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Display name", { exact: true })
    .fill("River learner");
  await dialog.getByLabel("Handle", { exact: true }).fill(handle);
  await dialog
    .getByLabel("Bio", { exact: true })
    .fill("Learning words for travel");
  await dialog
    .getByRole("button", { name: "Save profile", exact: true })
    .click();
  await expect(page).toHaveURL(new RegExp(`/u/${handle}$`));
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "River learner", exact: true }),
  ).toBeVisible();
  expect(await api.call<Account>("me")).toMatchObject({
    handle,
    display_name: "River learner",
    bio: "Learning words for travel",
  });
  const guest = await Api.create();
  try {
    expect(
      await guest.call<Account>(`users:lookup?handle=${handle}`),
    ).toMatchObject({ handle, display_name: "River learner" });
    await guest.call(
      `users:lookup?handle=${account.handle}`,
      "GET",
      undefined,
      404,
    );
  } finally {
    await guest.dispose();
  }
});

test("a duplicate handle preserves the unsaved profile draft", async ({
  user,
  secondary,
}) => {
  const { page } = user;
  const taken = `taken_${secondary.subject.slice(-10).toLowerCase()}`;
  await secondary.api.call("me/profile", "PATCH", { handle: taken });
  await page.goto(`/u/${user.account.id}`);
  await page.getByRole("button", { name: "Edit profile", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Display name", { exact: true }).fill("Unsaved name");
  await dialog.getByLabel("Handle", { exact: true }).fill(taken);
  await dialog
    .getByRole("button", { name: "Save profile", exact: true })
    .click();
  await expect(
    page.getByText("That handle is already taken. Choose another one.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(dialog.getByLabel("Display name", { exact: true })).toHaveValue(
    "Unsaved name",
  );
  expect(await user.api.call<Account>("me")).toMatchObject({
    handle: user.account.handle,
    display_name: user.account.display_name,
  });
});
