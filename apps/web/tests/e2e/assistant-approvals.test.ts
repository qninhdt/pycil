import { api } from './helpers/api'

import { randomUUID } from 'node:crypto'

import { expect,test } from './fixtures'

import type { Conversation,ConversationDetails } from '../../src/lib/assistant-api'

import type { AccountProfile } from '../../src/lib/api'

import { open,send } from './helpers/assistant'

test('Assistant auto-approval setting persists; a rejected write keeps the saved value', async ({ page, profile }) => {
  try {
    await page.goto('/app')
    await page.getByRole('button', { name: /^(Open PycilAI|PycilAI)$/ }).click()
    await page.getByRole('button', { name: 'AI settings' }).click()
    const toggle = page.getByRole('switch', { name: 'Auto-approve actions' })
    await expect(toggle).not.toBeChecked()
    await toggle.click()
    await expect(toggle).toBeChecked()
    expect((await api<AccountProfile>(page, 'me')).body.settings.assistant.auto_approve).toBe(true)
    await page.reload()
    await expect(page.getByRole('complementary', { name: 'PycilAI', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'AI settings' }).click()
    await expect(toggle).toBeChecked()
    await page.route('**/v1/me/settings', route => route.abort('connectionfailed'), { times: 1 })
    await toggle.click()
    await expect(toggle).toBeChecked()
    expect((await api<AccountProfile>(page, 'me')).body.settings.assistant.auto_approve).toBe(true)
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})

for (const decision of ['approve', 'reject'] as const) test(`pending native Library mutation survives reload and ${decision} changes only authorized data`, async ({ page, profile, nodes }) => {
  const title = 'assistant-' + randomUUID()
  const created = page.waitForResponse(r => r.url().endsWith('/assistant/conversations') && r.request().method() === 'POST')
  await open(page); await send(page, 'E2E create deck ' + title)
  const conversation: Conversation = await (await created).json()
  try {
    await expect(page.getByRole('button', { name: 'Approve changes', exact: true })).toBeVisible()
    const lookup = async () => (await api<{ nodes: { id: string }[] }>(page, `nodes/${profile.personal_node_id}:search?q=${encodeURIComponent(title)}`)).body.nodes
    expect(await lookup()).toEqual([])
    const pending = (await api<ConversationDetails>(page, `assistant/conversations/${conversation.id}`)).body.state.pending_approvals
    expect(pending).toHaveLength(1)
    await page.reload(); await open(page)
    await expect(page.getByRole('button', { name: 'Approve changes', exact: true })).toBeVisible()
    expect((await api<ConversationDetails>(page, `assistant/conversations/${conversation.id}`)).body.state.pending_approvals).toEqual(pending)
    const resumed = page.waitForResponse(response => response.url().endsWith('/assistant:run') && response.request().method() === 'POST')
    await page.getByRole('button', { name: decision === 'approve' ? 'Approve changes' : 'Reject', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Approve changes', exact: true })).not.toBeVisible()
    await expect.poll(async () => (await api<ConversationDetails>(page, `assistant/conversations/${conversation.id}`)).body.state.pending_approvals.length).toBe(0)
    const response = await resumed
    expect(response.status()).toBe(200)
    const stream = await response.text()
    expect(stream).toContain('RUN_FINISHED')
    expect(stream).not.toContain('RUN_ERROR')
    const result = await lookup()
    expect(result).toHaveLength(decision === 'approve' ? 1 : 0)
    if (result.length) { nodes.track(result[0].id); await page.goto(`/app/personal/${result[0].id}`); await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible() }
  } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
})
