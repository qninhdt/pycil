import { Icon } from '@/components/artwork/artwork'
import type { LibraryNode } from '@/lib/home-api'
import { libraryNodeKind } from '@/lib/library-model'

export function LibraryNodeIcon({ node }: { node: LibraryNode }) {
  const kind = libraryNodeKind(node)
  const name = node.type === 'REFERENCE'
    ? kind === 'DECK' ? 'deck-reference' : kind === 'FOLDER' ? 'folder-reference' : 'document'
    : kind === 'DECK' ? 'collection'
      : node.name === 'Personal' ? 'folder-personal'
        : node.name === 'Published' ? 'folder-published'
          : 'folder'
  // Unavailable sources have no reliable type; never guess or expose target details.
  return <Icon name={name} data-art-icon={name} />
}
