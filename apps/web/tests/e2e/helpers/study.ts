import type { Page } from '@playwright/test'
import { expect } from '@playwright/test'
import type { StudySession } from '../../../src/lib/study-session'

export async function session(page: Page, id: string, node = new URL(page.url()).searchParams.get('node')) {
  if (!node) throw new Error('Read a study session with an explicit node or a focus URL.')
  return page.evaluate(({ id, node }) => JSON.parse(localStorage.getItem(`pycil:study:${id}:${node}`) || 'null') as StudySession | null, { id, node })
}

export async function start(page: Page, node: string, selection = 'auto') {
  await page.goto(`/app/learn?node=${node}&selection=${selection}`)
  await expect(page.getByRole('button', { name: 'I don’t know', exact: true })).toBeVisible()
}

export async function finish(page: Page, id: string, unknownFirst = false, typedAnswer?: string) {
  for (let turn = 0; turn < 60; turn++) {
    const saved = await session(page, id)
    expect(saved).not.toBeNull()
    if (saved!.phase === 'complete' || saved!.phase === 'submitting') return saved!
    if (saved!.phase === 'recap') { await page.getByRole('button', { name: /^Continue to round/ }).click(); continue }
    if (saved!.phase === 'feedback') { await page.getByRole('button', { name: 'Continue', exact: true }).click(); continue }
    const item = saved!.prepared.bundles.flatMap(bundle => bundle.questions)[saved!.questions[saved!.position]]
    if (unknownFirst && turn === 0) await page.getByRole('button', { name: 'I don’t know', exact: true }).click()
    else {
      if (item.format === 'single_choice') {
        const index = item.options.findIndex(option => option.id === item.question.correct.id)
        expect(index).toBeGreaterThanOrEqual(0)
        await page.locator('.focus-options button').nth(index).click()
      } else {
        await page.getByRole('textbox', { name: item.format === 'single_word' ? 'Your word' : item.question.question_type === 'sentence_rewrite' ? 'Your rewrite' : 'Your answer' }).fill(typedAnswer ?? item.question.correct.content)
        await page.getByRole('button', { name: 'Check answer', exact: true }).click()
      }
    }
    await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeVisible()
  }
  throw new Error('The native quiz did not terminate within its attempt limit.')
}
