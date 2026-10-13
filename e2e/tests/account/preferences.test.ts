import { test, expect } from "../../fixtures/index.ts";
import type { Account } from "../../support/api.ts";

test("timezone preferences persist through the browser without changing other settings", async ({
  actor,
}) => {
  const { page, api } = actor;
  await page.goto("/app/settings");
  await page.getByLabel(/Time zone/).fill("Asia/Tokyo");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByText("Settings saved", { exact: true })).toBeVisible();
  const saved = await api.call<Account>("me");
  expect(saved.settings).toMatchObject({
    timezone: "Asia/Tokyo",
    locale: actor.account.settings.locale,
    translation_language: actor.account.settings.translation_language,
  });
  await page.reload();
  await expect(page.getByLabel(/Time zone/)).toHaveValue("Asia/Tokyo");
});

test("a failed settings write keeps the draft available for an explicit retry", async ({
  actor,
}) => {
  const { page, api } = actor;
  await page.goto("/app/settings");
  await page.getByLabel(/Time zone/).fill("Europe/London");
  await page.route("**/v1/me/settings", (route) =>
    route.request().method() === "PATCH"
      ? route.abort("connectionfailed")
      : route.continue(),
  );
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Save changes", exact: true }),
  ).toBeEnabled();
  await expect(page.getByLabel(/Time zone/)).toHaveValue("Europe/London");
  expect((await api.call<Account>("me")).settings.timezone).toBe(
    actor.account.settings.timezone,
  );
  await page.unroute("**/v1/me/settings");
  await page.getByRole("button", { name: "Save changes", exact: true }).click();
  await expect(page.getByText("Settings saved", { exact: true })).toBeVisible();
  expect((await api.call<Account>("me")).settings.timezone).toBe(
    "Europe/London",
  );
});

test('Free disables typed formats while Pro can save a compatible typed learning selection', async ({ actor, data }) => {
  await actor.page.goto('/app/settings')
  await actor.page.getByRole('button', { name: 'Learning', exact: true }).click()
  const typed = actor.page.getByRole('checkbox', { name: /Single word/ })
  await expect(typed).toBeDisabled()
  await expect(actor.page.getByText('Your Free plan uses multiple choice. The two typed formats are available on Pro.', { exact: true })).toBeVisible()
  await data.prepareActor({ plan: 'pro' })
  await actor.page.reload()
  await actor.page.getByRole('button', { name: 'Learning', exact: true }).click()
  await expect(typed).toBeEnabled()
  await typed.check()
  await actor.page.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(actor.page.getByText('Settings saved', { exact: true })).toBeVisible()
  const saved = await actor.api.call<{ settings: { learning: { formats: string[] } } }>('me')
  expect(saved.settings.learning.formats).toContain('single_word')
  await actor.page.reload()
  await actor.page.getByRole('button', { name: 'Learning', exact: true }).click()
  await expect(typed).toBeChecked()
})

test('interface and translation languages persist separately and reload renders the saved locale', async ({ actor }) => {
  await actor.page.goto('/app/settings')
  await actor.page.getByLabel(/Interface language/).selectOption('vi')
  await actor.page.getByLabel(/Translation language/).selectOption('en')
  const saved = actor.page.waitForResponse(response => response.url().endsWith('/me/settings') && response.request().method() === 'PATCH')
  await actor.page.getByRole('button', { name: 'Save changes', exact: true }).click()
  expect((await saved).status()).toBe(200)
  expect(await actor.api.call('me')).toMatchObject({ settings: { locale: 'vi', translation_language: 'en' } })
  await actor.page.reload()
  await expect(actor.page.locator('html')).toHaveAttribute('lang', 'vi')
})
