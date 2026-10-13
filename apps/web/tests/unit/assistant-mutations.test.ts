import { expect, test } from 'vitest'
import { toolMutation } from '../../src/features/assistant/mutations'

test('only successful tool writes invalidate domain queries', () => {
  for (const content of ['invalid', 'null', '[]', '{"error":"denied"}']) {
    expect(toolMutation('create_node', content)).toBeNull()
  }
  expect(toolMutation('read_library', '{"nodes":[]}')).toBeNull()
  expect(toolMutation('create_node', '{"id":"node"}')).toBe('library')
  expect(toolMutation('update_preferences', '{"settings":{}}')).toBe('preferences')
  expect(toolMutation('generate_words', '{"generations":[]}')).toBe('vocabulary')
  expect(toolMutation('delete_nodes', '{"items":[{"status":"failed","error":"denied"}]}')).toBeNull()
  expect(toolMutation('move_nodes', '{"items":[{"status":"failed"},{"status":"succeeded"}]}')).toBe('library')
})
