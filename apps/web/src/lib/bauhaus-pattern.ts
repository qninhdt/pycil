export type PatternBlock = {
  motif: 'orbit' | 'arch' | 'diagonal' | 'steps'
  rotation: number
  primary: number
  secondary: number
}

function seededRandom(seed: string | number) {
  let state = 2166136261
  for (const character of String(seed)) state = Math.imul(state ^ character.charCodeAt(0), 16777619) >>> 0
  return () => {
    state = (state + 0x6D2B79F5) >>> 0
    let value = Math.imul(state ^ (state >>> 15), state | 1)
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61)
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296
  }
}

export function generateBauhausPattern(seed: string | number, count = 32): PatternBlock[] {
  const next = seededRandom(seed)
  const motifs = ['orbit', 'arch', 'diagonal', 'steps'] as const
  const offset = Math.floor(next() * 4)
  let previous = Math.floor(next() * 4)
  return Array.from({ length: count }, (_, index) => {
    // Choose complete 2×2 compositions, never independent random tiles.
    // Neighbours change motif; a four-block colour cycle keeps the strip balanced.
    const motif = (previous + 1 + Math.floor(next() * 3)) % 4
    previous = motif
    const primary = (offset + index) % 4
    return {
      motif: motifs[motif],
      rotation: Math.floor(next() * 4) * 90,
      primary,
      secondary: (primary + 1 + Math.floor(next() * 3)) % 4,
    }
  })
}
