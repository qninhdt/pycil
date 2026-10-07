import type { ComponentProps } from 'react'
import { generateBauhausPattern, type PatternBlock } from '@/lib/bauhaus-pattern'
import { FitTileStrip } from './fit-tile-strip'
import { stripCapacity } from '@/lib/tile-strip'

const red = 'var(--art-red)'
const blue = 'var(--art-blue)'
const yellow = 'var(--art-yellow)'
const ink = 'var(--art-ink)'
const paper = 'var(--art-paper)'
const colors = [red, blue, yellow, ink]

function Block({ block }: { block: PatternBlock }) {
  const primary = colors[block.primary]
  const secondary = colors[block.secondary]
  switch (block.motif) {
    case 'orbit': return <>
      <path d="M16 0A16 16 0 0 0 0 16H16Z M16 32A16 16 0 0 0 32 16H16Z" fill={primary} />
      <path d="M16 0A16 16 0 0 1 32 16H16Z M16 32A16 16 0 0 1 0 16H16Z" fill={secondary} />
    </>
    case 'arch': return <>
      <rect width="32" height="32" fill={secondary} />
      <path d="M0 32A32 32 0 0 1 32 0V32Z" fill={primary} />
      <path d="M16 32A16 16 0 0 1 32 16V32Z" fill={paper} />
    </>
    case 'diagonal': return <>
      <path d="M0 0H16L32 16V32H16L0 16Z" fill={primary} />
      <path d="M16 0H32V16Z" fill={secondary} />
    </>
    case 'steps': return <>
      <path d="M0 0H16V16H32V32H16V16H0Z" fill={primary} />
      <path d="M16 0H32V16H16Z" fill={secondary} />
      <path d="M0 16V32H16Z" fill={secondary} />
    </>
  }
}

export function PatternPanel({ seed = 'pycil-1923', className, ...props }: Omit<ComponentProps<'div'>, 'children'> & { seed?: string | number }) {
  const blocks = generateBauhausPattern(seed, stripCapacity[32])
  return <FitTileStrip {...props} aria-hidden="true" className={className} tileSize={32} tiles={blocks.map((block, index) =>
    <svg key={index} width="100%" height="100%" viewBox="0 0 32 32" preserveAspectRatio="none" className="block" focusable="false" aria-hidden="true" data-pattern-block="">
      <rect width="32" height="32" fill={paper} />
      <g transform={`rotate(${block.rotation} 16 16)`}><Block block={block} /></g>
    </svg>
  )} />
}
