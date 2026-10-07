import type { BackgroundName } from '../components/artwork/artwork'

// Pin the existing 16 designs and their order: adding gallery art must not remap cards.
export const flashcardBackgrounds = [
  'archway-poster', 'tangent-field', 'stepped-horizon', 'split-disc-field',
  'suspended-orbits', 'cantilever-field', 'window-study', 'quiet-tangents',
  'primary-poster', 'editorial-axis', 'corner-study', 'modular-field',
  'orbital-field', 'diagonal-plane', 'quiet-construction', 'inverse-poster',
] as const satisfies readonly BackgroundName[]

// The seed selects existing artwork only; it never generates or mutates geometry.
export function flashcardArtwork(cardId: string | number): BackgroundName {
  let hash = 2166136261
  for (const char of String(cardId)) {
    hash ^= char.codePointAt(0)!
    hash = Math.imul(hash, 16777619)
  }
  hash ^= hash >>> 16
  hash = Math.imul(hash, 0x85ebca6b)
  hash ^= hash >>> 13
  hash = Math.imul(hash, 0xc2b2ae35)
  hash = (hash ^ hash >>> 16) >>> 0
  return flashcardBackgrounds[hash % flashcardBackgrounds.length]
}
