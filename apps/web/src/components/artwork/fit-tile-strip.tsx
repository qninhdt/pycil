import type { ComponentProps, ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { tileStripStyles } from '@/lib/tile-strip'

export function FitTileStrip({ tileSize, tiles, className, style, ...props }: Omit<ComponentProps<'div'>, 'children'> & { tileSize: 32; tiles: ReactNode[] }) {
  return <div {...props} className={cn(`fit-tile-strip-${tileSize} w-full shrink-0`, className)} style={{ ...style, height: tileSize, containerType: 'inline-size', containerName: `pycil-strip-${tileSize}` }}>
    <style>{tileStripStyles[tileSize]}</style>
    <div className="fit-tile-grid">
      {tiles.map((tile, index) => <div key={index} className="fit-tile" aria-hidden="true">{tile}</div>)}
    </div>
  </div>
}
