import type { ThreadMessage } from '@assistant-ui/react'

export function mergeAssistantTurns(messages: readonly ThreadMessage[], snapshot: readonly ThreadMessage[] = []): ThreadMessage[] {
  const saved = new Map(snapshot.map(message => [message.id, message]))
  const turns: ThreadMessage[] = []
  for (const live of messages) {
    const canonical = saved.get(live.id)
    // AG-UI's final run update can overwrite reasoning imported from its message snapshot.
    const message = live.role === 'assistant' && live.status.type === 'complete' && canonical?.role === 'assistant'
      ? { ...live, content: canonical.content }
      : live
    const previous = turns.at(-1)
    if (previous?.role === 'assistant' && message.role === 'assistant') {
      turns[turns.length - 1] = {
        ...previous,
        content: [...previous.content, ...message.content],
        status: message.status,
        metadata: { ...previous.metadata, ...message.metadata },
      }
    } else turns.push(message)
  }
  return turns
}
