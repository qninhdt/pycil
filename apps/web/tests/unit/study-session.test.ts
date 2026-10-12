import { expect,test } from 'vitest'

import { preparation } from './fixtures'

import { advanceSession,beginAttempt,createStudySession,currentQuestion,diagnosticComplete,finishSession,recordAttempt,startNextRound } from '../../src/lib/study-session'

test('retry recovery preserves the initial diagnostics and duplicated artifact occurrences', async () => {
  const prepared = preparation(1, 'SINGLE_CHOICE', 2)
  prepared.bundles[0].questions[1] = structuredClone(prepared.bundles[0].questions[0])
  let session = createStudySession('preview-alex', prepared)
  const firstOccurrence = session.questions[0]
  session = advanceSession(recordAttempt(beginAttempt(session, null), { correct: false }))
  session = advanceSession(recordAttempt(beginAttempt(session, currentQuestion(session)!.question.correct.id), { correct: true }))
  expect(session.phase).toBe('recap')
  session = startNextRound(session)
  expect(session.questions).toEqual([firstOccurrence])
  session = advanceSession(recordAttempt(beginAttempt(session, currentQuestion(session)!.question.correct.id), { correct: true }))
  expect(session.phase).toBe('submitting')
  expect(session.submission!.results).toHaveLength(2)
  expect(session.submission!.results.map(result => result.diagnostics)).toContainEqual({ correct: false })
  expect(session.submission!.results.map(result => result.diagnostics)).toContainEqual({ correct: true })
  expect(finishSession(session).submission).toBe(session.submission)
})

test('a grading failure keeps its locked answer and time without using a practice attempt', async () => {
  const prepared = preparation(1, 'SINGLE_WORD')
  const locked = beginAttempt(createStudySession('preview-alex', prepared), 'bank', new Date('2026-10-11T00:00:00Z'))
  expect(beginAttempt(locked, 'a different answer')).toEqual(locked)
  expect(locked.attempts).toEqual({})
  const graded = recordAttempt(locked, { task_fit: true, spelling_error: false, sense_id: 999 })
  expect(graded.attempts[graded.questions[0]][0]).toMatchObject({ answer: 'bank', answered_at: '2026-10-11T00:00:00.000Z', complete: true })
  expect(finishSession(graded).submission!.results[0].diagnostics).toMatchObject({ sense_id: 999 })
})

test('only two retries are allowed and partial completion submits completed initial evidence', async () => {
  const prepared = preparation()
  let session = createStudySession('preview-alex', prepared)
  for (let attempt = 0; attempt < 3; attempt++) {
    session = advanceSession(recordAttempt(beginAttempt(session, null), { correct: false }))
    if (attempt < 2) session = startNextRound(session)
  }
  expect(session.phase).toBe('submitting')
  expect(Object.values(session.attempts)[0]).toHaveLength(3)
  expect(session.submission!.results).toHaveLength(1)
  expect(session.submission!.results[0]).not.toHaveProperty('answer')
  expect(diagnosticComplete({ task_fit: true, spelling_error: true, sense_id: 1 })).toBe(false)
})

test('unseen occurrences continue across rounds and each occurrence submits once', () => {
  let session = createStudySession('account', preparation(10))
  expect(session.questions).toHaveLength(8)
  expect(session.unseen).toHaveLength(2)
  for (let index = 0; index < 8; index++) session = advanceSession(recordAttempt(beginAttempt(session, 'correct'), { correct: true }))
  expect(session.phase).toBe('recap')
  session = startNextRound(session)
  expect(session.questions).toHaveLength(2)
  for (let index = 0; index < 2; index++) session = advanceSession(recordAttempt(beginAttempt(session, 'correct'), { correct: true }))
  expect(session.phase).toBe('submitting')
  expect(new Set(session.submission!.results.map(result => result.question_artifact_id)).size).toBe(10)
  expect(finishSession(session).submission!.key).toBe(session.submission!.key)
})

test('invalid transitions and empty saves reject without changing the session', () => {
  const session = createStudySession('account', preparation(2))
  const before = structuredClone(session)
  expect(() => beginAttempt(session, '  ')).toThrow('Choose or enter')
  expect(() => recordAttempt(session, { correct: true })).toThrow('Lock the answer')
  expect(() => advanceSession(session)).toThrow('Finish the current answer')
  expect(() => startNextRound(session)).toThrow('Round is not complete')
  expect(() => finishSession(session)).toThrow('Answer a question')
  expect(session).toEqual(before)
  const partial = finishSession(recordAttempt(beginAttempt(session, 'correct'), { correct: true }))
  expect(partial.submission!.results).toHaveLength(1)
  expect(finishSession(partial).submission).toBe(partial.submission)
})
