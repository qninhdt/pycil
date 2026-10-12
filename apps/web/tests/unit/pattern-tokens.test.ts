import { expect,test } from 'vitest'

import { parsePatternTokens } from '../../src/components/dictionary/pattern-badge'

test('grammar pattern tokenizer decomposes formulas into semantic slots and connectors', () => {
  const t1 = parsePatternTokens('hard {sth}', 'hard')
  expect(t1).toEqual([
    { type: 'word', text: 'hard', isLemma: true, isConnector: false },
    { type: 'slot', slot: expect.objectContaining({ code: 'sth', label: 'sth' }) },
  ])

  const t2 = parsePatternTokens('hard to {do}', 'hard')
  expect(t2).toEqual([
    { type: 'word', text: 'hard', isLemma: true, isConnector: false },
    { type: 'word', text: 'to', isLemma: false, isConnector: true },
    { type: 'slot', slot: expect.objectContaining({ code: 'do', label: 'do' }) },
  ])

  const t3 = parsePatternTokens('hard for {sb} to {do}', 'hard')
  expect(t3).toEqual([
    { type: 'word', text: 'hard', isLemma: true, isConnector: false },
    { type: 'word', text: 'for', isLemma: false, isConnector: true },
    { type: 'slot', slot: expect.objectContaining({ code: 'sb', label: 'sb' }) },
    { type: 'word', text: 'to', isLemma: false, isConnector: true },
    { type: 'slot', slot: expect.objectContaining({ code: 'do', label: 'do' }) },
  ])

  const t4 = parsePatternTokens('hard {doing}', 'hard')
  expect(t4).toEqual([
    { type: 'word', text: 'hard', isLemma: true, isConnector: false },
    { type: 'slot', slot: expect.objectContaining({ code: 'doing', label: 'doing' }) },
  ])

  const t5 = parsePatternTokens('hard on {sb}', 'hard')
  expect(t5).toEqual([
    { type: 'word', text: 'hard', isLemma: true, isConnector: false },
    { type: 'word', text: 'on', isLemma: false, isConnector: true },
    { type: 'slot', slot: expect.objectContaining({ code: 'sb', label: 'sb' }) },
  ])

  const t6 = parsePatternTokens("trait of {one's} personality", 'trait')
  expect(t6).toEqual([
    { type: 'word', text: 'trait', isLemma: true, isConnector: false },
    { type: 'word', text: 'of', isLemma: false, isConnector: true },
    { type: 'slot', slot: expect.objectContaining({ code: "one's", label: "one's" }) },
    { type: 'word', text: 'personality', isLemma: false, isConnector: false },
  ])
})
