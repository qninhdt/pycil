import { afterEach,beforeEach,expect,test,vi } from 'vitest'
import { createStudySession,discardSession,listActiveSessions,loadSession,pruneStaleSessions,saveSession,sessionKey } from '../../src/lib/study-session'
import { preparation } from './fixtures'

let values: Map<string, string>
beforeEach(() => {
  values = new Map()
  vi.stubGlobal('localStorage', {
    get length() { return values.size },
    key: (index: number) => [...values.keys()][index] ?? null,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value) },
    removeItem: (key: string) => { values.delete(key) },
  })
})
afterEach(() => vi.unstubAllGlobals())

test('round trip is account and node scoped and preserves prepared data', () => {
  const session = createStudySession('account', preparation())
  saveSession(session)
  expect(loadSession('account', 'deck')).toMatchObject({ ...session, updated_at: expect.any(String) })
  expect(Date.parse(loadSession('account', 'deck')!.updated_at!)).toBeGreaterThanOrEqual(Date.parse(session.updated_at!))
  expect(loadSession('other', 'deck')).toBeNull()
  expect(loadSession('account', 'other')).toBeNull()
  expect(listActiveSessions('account')).toEqual(['deck'])
  expect(listActiveSessions('other')).toEqual([])
  discardSession('account', 'deck')
  expect(loadSession('account', 'deck')).toBeNull()
})

test('malformed persisted sessions are rejected before reuse', () => {
  const session = createStudySession('account', preparation())
  const corruptions = ['{', 'null', ...[
    { version: 1 }, { accountId: 'other' }, { prepared: { ...session.prepared, node_id: 'other' } },
    { questions: [999] }, { unseen: [-1] }, { retry: ['0'] }, { position: 999 },
    { phase: 'unknown' }, { attempts: { 0: [{}] } }, { prepared: { ...session.prepared, actual_question_count: 9 } },
  ].map(patch => JSON.stringify({ ...session, ...patch }))]
  for (const value of corruptions) {
    values.set(sessionKey('account', 'deck'), value)
    expect(loadSession('account', 'deck')).toBeNull()
  }
})

test('blocked storage reads recover and write failure remains visible to the caller', () => {
  vi.stubGlobal('localStorage', {
    getItem() { throw new Error('blocked') },
    setItem() { throw new Error('quota') },
    removeItem() { throw new Error('blocked') },
    get length() { throw new Error('blocked') },
  })
  expect(loadSession('account', 'deck')).toBeNull()
  expect(listActiveSessions('account')).toEqual([])
  expect(() => saveSession(createStudySession('account', preparation()))).toThrow('quota')
  expect(() => discardSession('account', 'deck')).not.toThrow()
  expect(() => pruneStaleSessions('account')).not.toThrow()
})

test('pruning removes adjacent stale and corrupt keys without deleting other accounts or fresh sessions', () => {
  for (const node of ['first', 'second', 'third']) values.set(sessionKey('account', node), JSON.stringify({ updated_at: '2000-01-01T00:00:00Z' }))
  values.set(sessionKey('account', 'corrupt'), '{')
  values.set(sessionKey('other', 'stale'), JSON.stringify({ updated_at: '2000-01-01T00:00:00Z' }))
  values.set(sessionKey('account', 'fresh'), JSON.stringify({ updated_at: new Date().toISOString() }))
  pruneStaleSessions('account')
  expect([...values.keys()]).toEqual([sessionKey('other', 'stale'), sessionKey('account', 'fresh')])
})
