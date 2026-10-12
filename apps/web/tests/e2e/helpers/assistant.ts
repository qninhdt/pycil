import { expect,type Page } from '@playwright/test'

export async function open(page: Page) {
  const panel = page.getByRole('complementary', { name: 'PycilAI', exact: true })
  const launcher = page.locator('html[data-ai-open="false"]').getByRole('button', { name: 'Open PycilAI', exact: true })
  await expect.poll(async () => await panel.isVisible() || (await launcher.isVisible() && await launcher.isEnabled())).toBe(true)
  if (!await panel.isVisible()) await launcher.click()
  await expect(page.getByRole('textbox', { name: 'Message PycilAI' })).toBeVisible()
}

export async function send(page: Page, message: string) {
  await page.getByRole('textbox', { name: 'Message PycilAI' }).fill(message)
  await page.getByRole('button', { name: 'Send message', exact: true }).click()
}
