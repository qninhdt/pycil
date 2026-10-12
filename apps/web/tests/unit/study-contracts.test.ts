import { expect,test } from 'vitest'
import { HomeApiError,parsePreparation } from '../../src/lib/home-api'
import { preparation } from './fixtures'

test('preparation validates counts, limits, native identities and queue inputs', () => {
  const valid = preparation(2)
  expect(parsePreparation(valid)).toEqual(valid)
  for (const patch of [
    { actual_sense_count: 9 }, { actual_question_count: 9 }, { selection: 'invented' }, { max_sense_count: 21 },
    { bundles: [valid.bundles[0], valid.bundles[0]] },
    { bundles: [{ ...valid.bundles[0], reason: 'unknown' }] },
    { preferences: { ...valid.preferences, formats: ['UNKNOWN'] } },
    { preferences: { ...valid.preferences, questions_per_sense: 4 } },
  ]) expect(() => parsePreparation({ ...valid, ...patch })).toThrow(HomeApiError)
  const wrongSense = structuredClone(valid)
  wrongSense.bundles[0].questions[0].question.sense_id = 999
  expect(() => parsePreparation(wrongSense)).toThrow(HomeApiError)
})

test('empty scopes require zero questions rather than invented data', () => {
  expect(parsePreparation({ ...preparation(), actual_sense_count: 0, actual_question_count: 0, bundles: [] }).bundles).toEqual([])
  expect(() => parsePreparation({ node_id: 'root', selection: 'DUE', actual_sense_count: 0, actual_question_count: 3 })).toThrow(HomeApiError)
})
