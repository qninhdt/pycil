export type AssistantMutation = 'library' | 'vocabulary' | 'preferences'

export function toolMutation(name: string, content: string): AssistantMutation | null {
  let value: unknown
  try { value = JSON.parse(content) } catch { return null }
  if (!value || typeof value !== 'object' || Array.isArray(value) || 'error' in value) return null
  if ('items' in value && (!Array.isArray(value.items) || !value.items.some(item => item && typeof item === 'object' && item.status === 'succeeded'))) return null
  if (['create_node', 'update_node', 'move_nodes', 'copy_nodes', 'delete_nodes'].includes(name)) return 'library'
  if (name === 'generate_words') return 'vocabulary'
  if (name === 'update_preferences') return 'preferences'
  return null
}
