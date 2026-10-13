import { Icon, iconNames, compactIconNames, learningIconNames, displayName, type IconName, type CompactIconName, type LearningIconName } from '@/components/artwork/artwork'
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty'
import { CopyButton, SectionIntro } from './specimen'

const normalize = (value: string) => value.toLowerCase().replaceAll(/[\s_-]+/g, '')

function IconSection({ id, title, description, names, variant, size }: {
  id: string; title: string; description: string; names: readonly (IconName | CompactIconName | LearningIconName)[]; variant: 'art' | 'control' | 'learning'; size: string
}) {
  if (!names.length) return null
  const kind = variant === 'art' ? 'identity' : variant
  return <section id={id}>
    <SectionIntro title={title} description={description} />
    <div className="grid grid-cols-6 border-t border-l border-border max-[1100px]:grid-cols-3 max-md:grid-cols-2">
      {names.map(name => <article className="art-tile icon-tile min-w-0 border-r border-b border-border bg-card" data-role={variant} key={name}>
        <div className="flex h-[100px] items-center justify-center gap-5 overflow-hidden text-[10px] text-muted-foreground">
          {(['color', 'mono'] as const).map(tone => <span className="grid min-w-11 justify-items-center gap-2" key={tone}>
            {variant === 'art' ? <Icon name={name as IconName} tone={tone} className={`catalog-icon ${size}`} /> : variant === 'control' ? <Icon name={name as CompactIconName} variant="control" tone={tone} className={`catalog-icon ${size}`} /> : <Icon name={name as LearningIconName} variant="learning" tone={tone} className={`catalog-icon ${size}`} />}
            <small>{tone === 'color' ? 'Color' : 'Mono'}</small>
          </span>)}
        </div>
        <div className="flex items-center justify-between gap-1 border-t border-border p-2 text-[10px] font-semibold break-words">
          <span>{displayName(variant === 'learning' ? name.toLowerCase().replaceAll('_', '-') : name)}</span>
          <CopyButton label={`Copy ${name} ${kind} icon usage`} text={`import { Icon } from '@/components/artwork/artwork'\n\n<Icon name="${name}"${variant === 'art' ? '' : ` variant="${variant}"`} tone="${variant === 'control' ? 'mono' : 'color'}" />`} />
        </div>
      </article>)}
    </div>
  </section>
}

export default function IconGallery({ query }: { query: string }) {
  const matches = (name: string) => normalize(name).includes(normalize(query).replace(/icon$/, ''))
  const art = iconNames.filter(matches)
  const controls = compactIconNames.filter(matches)
  const learning = learningIconNames.filter(matches)
  return <>
    <SectionIntro title="One icon language." description="Each color and mono pair shares one geometric construction. Compare both drawings at their intended sizes." />
    <IconSection id="identity-icons" title="Identity and content" description="Expressive icons for navigation, collections and content." names={art} variant="art" size="size-7" />
    <IconSection id="control-icons" title="Controls" description="Precise icons for buttons, inputs and menus. Mono is the default in dense controls." names={controls} variant="control" size="size-6" />
    <IconSection id="learning-icons" title="Learning" description="Question and answer format icons at settings size." names={learning} variant="learning" size="size-[34px]" />
    {!art.length && !controls.length && !learning.length && <Empty><EmptyHeader><EmptyTitle>No matching icons</EmptyTitle><EmptyDescription>Try a different name.</EmptyDescription></EmptyHeader></Empty>}
  </>
}
