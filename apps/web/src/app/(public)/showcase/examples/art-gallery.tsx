import { useState } from 'react'
import {
  Background, backgroundNames, displayName, Motif, motifNames,
  Shape, shapeNames,
} from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import { CopyButton, SectionIntro } from './specimen'

export function ArtGallery({ query }: { query: string }) {
  const [tone, setTone] = useState<'color' | 'mono'>('color')
  const matches = (name: string) => displayName(name).toLowerCase().includes(query.toLowerCase())
  const usage = (component: string, name: string) =>
    `import { ${component} } from '@/components/artwork/artwork'\n\n<${component} name="${name}"${tone === 'mono' ? ' tone="mono"' : ''} />`

  return (
    <>
      <SectionIntro title="Art, with intention." description="Hand-authored. Named. Ready to reuse. No generator, no random geometry.">
        <Button variant="outline" size="sm" onClick={() => setTone(tone === 'color' ? 'mono' : 'color')}>
          {tone === 'color' ? 'View monochrome' : 'View color'}
        </Button>
      </SectionIntro>
      <section id="motifs">
        <SectionIntro title="Motifs" description={`${motifNames.length} compact compositions: solids, outlines, counterforms and construction axes.`} />
        <div className="grid grid-cols-4 border-t border-l border-border [&.background-grid]:grid-cols-2 max-[1100px]:grid-cols-3 max-md:grid-cols-2 max-md:[&.background-grid]:grid-cols-1">
          {motifNames.filter(matches).map(name => (
            <article className="art-tile min-w-0 border-r border-b border-border bg-card" key={name}>
              <div className="h-40 flex items-center justify-center overflow-hidden [&_.bauhaus-icon[data-variant=art]]:size-[76px] [&_.bauhaus-motif]:max-w-[180px] [&_.bauhaus-motif]:h-[130px] max-md:h-[135px]"><Motif name={name} tone={tone} /></div>
              <div className="flex items-center justify-between border-t border-border px-3.5 py-2.5 text-xs font-semibold">
                <span>{displayName(name)}</span>
                <CopyButton label={`Copy ${name} motif usage`} text={usage('Motif', name)} />
              </div>
            </article>
          ))}
        </div>
      </section>
      <section id="backgrounds">
        <SectionIntro title="Backgrounds" description={`${backgroundNames.length} adaptive compositions. Shapes keep their proportions as the canvas and anchors follow the container.`} />
        <div className="grid grid-cols-4 border-t border-l border-border [&.background-grid]:grid-cols-2 max-[1100px]:grid-cols-3 max-md:grid-cols-2 max-md:[&.background-grid]:grid-cols-1">
          {backgroundNames.filter(matches).map(name => (
            <article className="art-tile min-w-0 border-r border-b border-border bg-card" key={name}>
              <div className="h-[230px] flex items-center justify-center overflow-hidden"><Background name={name} tone={tone} /></div>
              <div className="flex items-center justify-between border-t border-border px-3.5 py-2.5 text-xs font-semibold">
                <span>{displayName(name)}</span>
                <CopyButton label={`Copy ${name} background usage`} text={usage('Background', name)} />
              </div>
            </article>
          ))}
        </div>
      </section>
    </>
  )
}

const swatches = [
  { name: 'Alizarin', token: '--palette-primary-red' },
  { name: 'Peter River', token: '--palette-primary-blue' },
  { name: 'Sun Flower', token: '--palette-primary-yellow' },
  { name: 'Midnight Blue', token: '--palette-ink' },
  { name: 'Silver', token: '--palette-border' },
  { name: 'Clouds', token: '--palette-canvas' },
]

export function Foundations() {
  return (
    <>
      <SectionIntro title="A shared visual language." description="Flat UI Palette v1, Manrope and a precise editorial grid. Values come from DESIGN.md." />
      <div className="grid grid-cols-6 border border-border max-md:grid-cols-3">
        {swatches.map(s => (
          <div key={s.name} className="h-[130px] flex flex-col justify-end p-3.5 text-xs font-semibold [&_small]:block [&_small]:text-[10px] [&_small]:mt-1 max-md:h-[100px]" style={{ background: `var(${s.token})` }}>
            <div className="bg-[var(--palette-canvas)] text-[var(--palette-ink)] px-2 py-1.5"><span>{s.name}</span><small>{s.token.replace('--palette-', '')}</small></div>
          </div>
        ))}
      </div>
      <SectionIntro title="Typography" description="One geometric family. Hierarchy through scale, weight and proportion." />
      <div className="border-b border-border py-6 flex justify-between gap-5 items-center [&_small]:text-muted-foreground [&_small]:text-[11px]"><span className="text-[clamp(36px,5vw,64px)] font-extrabold tracking-[-.04em] leading-[1.05]">Form & function.</span><small>Manrope / 800</small></div>
      <div className="border-b border-border py-6 flex justify-between gap-5 items-center [&_small]:text-muted-foreground [&_small]:text-[11px]"><h3 className="text-3xl font-bold tracking-tight">Make room for ideas.</h3><small>Heading / 32</small></div>
      <div className="border-b border-border py-6 flex justify-between gap-5 items-center [&_small]:text-muted-foreground [&_small]:text-[11px]"><p className="text-base leading-relaxed">Useful interfaces can have a point of view.</p><small>Body / 16</small></div>
      <SectionIntro title="Geometric vocabulary" description="The building blocks are simple. Their relationships are where the design lives." />
      <div className="grid grid-cols-6 gap-5.5 py-8 max-md:grid-cols-3">
        {shapeNames.map(name => <div className="shape-spec text-center text-[11px] text-muted-foreground [&_svg]:size-16 [&_svg]:block [&_svg]:mx-auto [&_svg]:mb-4.5" key={name}><Shape name={name} />{displayName(name)}</div>)}
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed mt-4.5">Shape–state meaning belongs to the product using this theme. Decoration does not communicate a learning status.</p>
    </>
  )
}
