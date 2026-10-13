import { expect, type Page } from '@playwright/test'
import type { Actor } from '../fixtures/actors.ts'

export async function selectQuestions(actor: Actor, type = 'definition_to_word', format = 'single_choice') {
  await actor.api.call('me/settings', 'PATCH', { learning: { question_types: [type], formats: [format], questions_per_sense: 1, max_sense_count: 1 } })
}

export async function startStudy(page: Page, nodeId: string, selection: 'new' | 'due' | 'auto' = 'new') {
  await page.goto(`/app/learn?node=${nodeId}&selection=${selection}`)
  await expect(page.getByRole('button', { name: "I don’t know", exact: true })).toBeVisible()
}

export async function answerChoice(page: Page, answer: string) {
  // The expected text belongs to the authored dataset, not the prepared response.
  await page.getByRole('button').filter({ hasText: answer }).click()
  await expect(page.getByText('That fits.', { exact: true })).toBeVisible()
}

export async function finishStudy(page: Page) {
  await page.getByRole('button', { name: /^Continue/ }).click()
  await expect(page.getByRole('heading', { name: 'Session complete', exact: true })).toBeVisible()
}
