import { describe, expect, it } from 'vitest'
import type { AccountProfile } from '@/lib/api/account'
import { studyReturnHref } from '@/features/study/navigation'

const profile = { id: 'me', library_node_id: 'library', personal_node_id: 'personal', published_node_id: 'published' } as AccountProfile

describe('study return destination', () => {
  it.each([
    ['library', undefined, '/app'],
    ['', undefined, '/app'],
    ['personal', undefined, '/app/personal'],
    ['published', undefined, '/app/published'],
    ['deck', undefined, '/app/personal/deck'],
    ['folder', undefined, '/app/personal/folder'],
    ['deck', 'me', '/app/published/deck'],
    ['deck', 'other', '/u/other/deck'],
  ])('returns from %s (%s) to %s', (node, owner, expected) => {
    expect(studyReturnHref(node, profile, owner)).toBe(expected)
  })
})
