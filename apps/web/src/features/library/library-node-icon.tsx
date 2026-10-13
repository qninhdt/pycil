import { Icon } from '@/components/artwork/artwork'
import type { LibraryNode } from '@/lib/api/study'
import { libraryNodeKind } from '@/features/library/model'

export function LibraryNodeIcon({ node }: { node: LibraryNode }) {
  const kind = libraryNodeKind(node)
  const name = node.type === 'reference'
    ? kind === 'deck' ? 'deck-reference' : kind === 'folder' ? 'folder-reference' : 'document'
    : kind === 'deck' ? 'collection'
      : node.name === 'Personal' ? 'folder-personal'
        : node.name === 'Published' ? 'folder-published'
          : 'folder'
  // Unavailable sources have no reliable type; never guess or expose target details.
  return <Icon name={name} data-art-icon={name} />
}
