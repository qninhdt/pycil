import { forwardRef, type ReactNode, type SVGProps } from 'react'
import { cn } from '@/lib/utils'
import { compactIcons } from './icon-glyphs'
import { identityIcons } from './identity-icon-glyphs'
import { learningIcons } from './learning-icon-glyphs'

// Hand-authored paths. No randomness, product semantics, external assets or SVG IDs.
const R = 'var(--art-red)', B = 'var(--art-blue)', Y = 'var(--art-yellow)'
const I = 'var(--art-ink)', P = 'var(--art-paper)'
const shapes = {
  circle: <circle cx="32" cy="32" r="28" fill={R} />,
  square: <rect x="5" y="5" width="54" height="54" fill={B} />,
  triangle: <path d="M32 4 62 58H2Z" fill={Y} />,
  arc: <path d="M60 60H4A56 56 0 0 1 60 4Z" fill={R} />,
  ring: <circle cx="32" cy="32" r="27" fill="none" stroke={I} strokeWidth="2" />,
  axis: <path d="M0 32h64M32 0v64" stroke={I} strokeWidth="1" />,
} satisfies Record<string, ReactNode>
const icons = identityIcons

const motifs = {
  'double-arch': <><path d="M15 104V50a35 35 0 0 1 70 0v54H65V50a15 15 0 0 0-30 0v54Z" fill={R}/><path d="M88 104V69a24 24 0 0 1 48 0v35h-17V69a7 7 0 0 0-14 0v35Z" fill={B}/><path d="M4 105h151" stroke={I}/></>,
  'tangent-study': <><circle cx="62" cy="59" r="42" fill={Y}/><circle cx="62" cy="59" r="25" fill={P}/><rect x="103" y="17" width="34" height="84" fill={B}/><path d="M9 17h142M9 101h142M62 5v109" stroke={I}/><circle cx="137" cy="101" r="9" fill={R}/></>,
  'three-planes': <><path d="m17 37 46-22v60l-46 22Z" fill={B}/><path d="m64 53 45-22v60l-45 22Z" fill={Y}/><path d="m109 31 33-17v60l-33 17Z" fill={R}/><path d="M17 105h126" stroke={I}/></>,
  'nested-corners': <><path d="M18 104V15h89v22H40v67Z" fill={B}/><path d="M50 104V47h89v22H72v35Z" fill={Y}/><circle cx="128" cy="23" r="15" fill={R}/></>,
  'cut-disc': <><circle cx="77" cy="60" r="47" fill={R}/><path d="M77 13v47h47Z" fill={P}/><path d="M77 60h47v47H77Z" fill={B}/><path d="M9 60h141M77 4v112" stroke={I}/></>,
  'cantilever': <><rect x="20" y="23" width="108" height="25" fill={B}/><rect x="66" y="48" width="24" height="56" fill={R}/><path d="m126 54 27 50h-54Z" fill={Y}/><path d="M5 104h150" stroke={I}/></>,
  'orbit-pair': <><circle cx="59" cy="60" r="38" fill="none" stroke={I}/><circle cx="100" cy="60" r="38" fill="none" stroke={I}/><circle cx="80" cy="27" r="16" fill={R}/><rect x="76" y="77" width="23" height="23" fill={B}/></>,
  'folded-ribbon': <><path d="M17 25h74L62 58H17Z" fill={B}/><path d="M62 58h75v34H32Z" fill={Y}/><path d="m91 25 46 33H62Z" fill={R}/><path d="M7 103h145" stroke={I}/></>,
  'cross-counterform': <><path d="M58 12h44v27h30v44h-30v27H58V83H28V39h30Z" fill={B}/><circle cx="80" cy="61" r="20" fill={P}/><circle cx="132" cy="22" r="12" fill={R}/></>,
  'quarter-turns': <><path d="M20 14h53v46A53 46 0 0 1 20 14Z" fill={R}/><path d="M86 14h53v46A53 46 0 0 1 86 14Z" fill={Y}/><path d="M20 106h53V60a53 46 0 0 0-53 46Z" fill={B}/><circle cx="111" cy="83" r="23" stroke={I} fill="none"/></>,
  'suspended-disc': <><path d="M26 4v108M132 4v108M6 80h148" stroke={I}/><circle cx="79" cy="40" r="32" fill={R}/><rect x="47" y="80" width="64" height="24" fill={B}/></>,
  'rhythm-study': <><rect x="17" y="17" width="17" height="87" fill={B}/><rect x="49" y="17" width="17" height="87" fill={B}/><path d="M81 17v87a43.5 43.5 0 0 0 0-87Z" fill={R}/><path d="M136 104V69l19 35Z" fill={Y}/></>,
  'split-diamond': <><path d="m80 9 52 51-52 51-52-51Z" fill={Y}/><path d="M80 9v102l52-51Z" fill={B}/><circle cx="80" cy="60" r="18" fill={P}/><path d="M7 60h146" stroke={I}/></>,
  'arch-window': <><path d="M33 108V52a47 47 0 0 1 94 0v56Z" fill={Y}/><path d="M56 108V52a24 24 0 0 1 48 0v56Z" fill={P}/><rect x="56" y="65" width="48" height="43" fill={B}/><circle cx="128" cy="21" r="12" fill={R}/></>,
  'diagonal-balance': <><path d="M15 104 139 16M15 16l124 88" stroke={I}/><circle cx="44" cy="36" r="25" fill={R}/><path d="m105 60 37 44H68Z" fill={Y}/><rect x="98" y="11" width="28" height="28" fill={B}/></>,
  'counterweight': <><path d="M12 25h136M80 5v105" stroke={I}/><rect x="26" y="25" width="30" height="67" fill={B}/><circle cx="112" cy="58" r="33" fill={R}/><path d="m80 86 12 24H68Z" fill={Y}/></>,
  orbit: <><circle cx="73" cy="65" r="39" fill="none" stroke={I}/><circle cx="44" cy="36" r="23" fill={R}/><rect x="108" y="72" width="30" height="30" fill={B}/><path d="M10 65h140" stroke={I}/></>,
  interlock: <><rect x="25" y="19" width="65" height="65" fill={B}/><circle cx="96" cy="72" r="34" fill="none" stroke={I}/><path d="M64 43h32v32H64Z" fill={Y}/></>,
  counterform: <><circle cx="69" cy="60" r="44" fill={R}/><circle cx="84" cy="47" r="27" fill={P}/><rect x="107" y="61" width="25" height="42" fill={B}/></>,
  'corner-disc': <><path d="M160 0v99A99 99 0 0 1 61 0Z" fill={R}/><rect x="19" y="46" width="31" height="74" fill={B}/><path d="M2 81h150M35 8v103" stroke={I}/></>,
  'offset-frame': <><rect x="20" y="20" width="76" height="76" fill="none" stroke={I}/><rect x="42" y="37" width="76" height="76" fill={Y}/><circle cx="118" cy="27" r="18" fill={B}/></>,
  axis: <><path d="M4 51h152M95 4v112" stroke={I}/><path d="M95 6v89A44.5 44.5 0 0 1 95 6Z" fill={R}/><rect x="95" y="6" width="34" height="89" fill={B}/></>,
  'folded-plane': <><path d="m22 48 48-27v72l-48 27Z" fill={Y}/><path d="m47 35 48-27v72L47 107Z" fill={B}/><path d="m72 47 48-27v72l-48 27Z" fill={R}/></>,
  'stepped-blocks': <><path d="M20 96V67h30V38h30V9h30v87Z" fill={B}/><path d="M49 96V67h31V38h30v58Z" fill={Y}/><rect x="109" y="67" width="30" height="29" fill={R}/></>,
  radial: <><circle cx="80" cy="60" r="46" fill="none" stroke={I}/><circle cx="80" cy="60" r="30" fill="none" stroke={I}/><circle cx="80" cy="60" r="13" fill={R}/><path d="M80 14a46 46 0 0 1 46 46H80Z" fill={B}/></>,
  'split-circle': <><path d="M80 16a44 44 0 0 0 0 88Z" fill={R}/><path d="M80 16a44 44 0 0 1 44 44H80Z" fill={B}/><path d="M80 60h44a44 44 0 0 1-44 44Z" fill={Y}/><path d="M9 60h142" stroke={I}/></>,
  bridge: <><path d="M22 101V57a45 45 0 0 1 90 0v44H88V57a21 21 0 0 0-42 0v44Z" fill={R}/><rect x="112" y="78" width="28" height="23" fill={B}/><path d="M6 101h148" stroke={I}/></>,
  balance: <><path d="M17 66h128M81 26v75" stroke={I}/><circle cx="44" cy="40" r="24" fill={R}/><path d="m108 22 28 44H80Z" fill={Y}/><rect x="61" y="89" width="40" height="13" fill={B}/></>,
  aperture: <><rect x="27" y="7" width="95" height="105" fill={B}/><circle cx="74" cy="60" r="33" fill={P}/><circle cx="111" cy="28" r="18" fill={R}/><path d="M74 6v106" stroke={I}/></>,
  modular: <><rect x="25" y="17" width="47" height="43" fill={B}/><path d="M119 17v43H72a47 43 0 0 1 47-43" fill={R}/><path d="M25 60h47v43Z" fill={Y}/><circle cx="96" cy="82" r="21" fill="none" stroke={I}/></>,
  horizon: <><circle cx="80" cy="54" r="37" fill={Y}/><rect x="20" y="55" width="120" height="40" fill={B}/><path d="M8 55h144M8 101h144" stroke={I}/><rect x="109" y="55" width="31" height="40" fill={R}/></>,
  'rising-bars': <><rect x="22" y="68" width="27" height="36" fill={Y}/><rect x="65" y="41" width="27" height="63" fill={R}/><rect x="109" y="13" width="27" height="91" fill={B}/><path d="M8 105h143" stroke={I}/></>,
} satisfies Record<string, ReactNode>

export { Background, backgroundNames, type BackgroundName } from './background'

export type IconName = keyof typeof icons
export type CompactIconName = keyof typeof compactIcons
export type LearningIconName = keyof typeof learningIcons
export type ShapeName = keyof typeof shapes
export const shapeNames = Object.keys(shapes) as ShapeName[]
export type MotifName = keyof typeof motifs
export const iconNames = Object.keys(icons) as IconName[]
export const compactIconNames = Object.keys(compactIcons) as CompactIconName[]
export const learningIconNames = Object.keys(learningIcons) as LearningIconName[]
export const motifNames = Object.keys(motifs) as MotifName[]
export const displayName = (name: string) => name.replaceAll('-', ' ').replace(/^./, c => c.toUpperCase())
type ArtProps = Omit<SVGProps<SVGSVGElement>, 'name'> & { tone?: 'color' | 'mono' }

export function Shape({ name, className, tone = 'color', ...props }: ArtProps & { name: ShapeName }) {
  return <svg viewBox="0 0 64 64" fill="none" className={cn('bauhaus-shape', className)} data-tone={tone} aria-hidden="true" {...props}>{shapes[name]}</svg>
}

type IconProps = Omit<SVGProps<SVGSVGElement>, 'name'> & { tone?: 'color' | 'mono'; size?: number | string } & (
  | { name: IconName; variant?: 'art' }
  | { name: CompactIconName; variant: 'control' }
  | { name: LearningIconName; variant: 'learning' }
)

export const Icon = forwardRef<SVGSVGElement, IconProps>(function Icon({ name, variant = 'art', tone, size, className, ...props }, ref) {
  const compact = variant === 'control'
  const learning = variant === 'learning'
  const resolvedTone = tone ?? (compact ? 'mono' : 'color')
  const mono = resolvedTone === 'mono'
  const rawGlyph = learning ? learningIcons[name as LearningIconName]
    : compact ? compactIcons[name as CompactIconName]
      : icons[name as IconName]
  const glyph = typeof rawGlyph === 'function' ? rawGlyph
    : typeof compactIcons[name as CompactIconName] === 'function' ? compactIcons[name as CompactIconName]
    : typeof icons[name as IconName] === 'function' ? icons[name as IconName]
    : typeof learningIcons[name as LearningIconName] === 'function' ? learningIcons[name as LearningIconName]
    : null

  if (!glyph) return null

  return <svg {...props} ref={ref} viewBox={compact ? '0 0 24 24' : '0 0 48 48'}
    width={size ?? (compact ? 24 : 48)} height={size ?? (compact ? 24 : 48)}
    fill="none" stroke="currentColor" strokeWidth={compact ? 1.8 : 2.8}
    strokeLinecap="square" strokeLinejoin="miter"
    className={cn('bauhaus-icon', compact && 'bauhaus-icon--control', className)} data-variant={variant} data-tone={resolvedTone}
    aria-hidden={props['aria-hidden'] ?? true}>{glyph(mono)}</svg>
})

function controlIcon(name: CompactIconName) {
  return forwardRef<SVGSVGElement, Omit<IconProps, 'name' | 'variant'>>(function NamedIcon(props, ref) {
    return <Icon {...props} variant="control" name={name} ref={ref} />
  })
}

export const ArrowRight = controlIcon('arrow-right'), ArrowLeft = controlIcon('arrow-left'), ArrowUpRight = controlIcon('arrow-up-right'), ArrowUpLeft = controlIcon('arrow-up-left')
export const ArrowDownIcon = controlIcon('arrow-down'), ArrowUpDown = controlIcon('arrow-up-down')
export const ChevronRight = controlIcon('chevron-right'), ChevronRightIcon = ChevronRight, ChevronLeftIcon = controlIcon('chevron-left')
export const ChevronUpIcon = controlIcon('chevron-up'), ChevronDown = controlIcon('chevron-down'), ChevronDownIcon = ChevronDown
export const Check = controlIcon('check'), CheckIcon = Check, X = controlIcon('x'), XIcon = X
export const Plus = controlIcon('plus'), Minus = controlIcon('minus'), MinusIcon = Minus
export const MoreHorizontal = controlIcon('more'), MoreHorizontalIcon = MoreHorizontal
export const Search = controlIcon('search'), SearchIcon = Search, Menu = controlIcon('menu'), PanelLeftIcon = controlIcon('panel-left')
export const LayoutGrid = controlIcon('grid'), List = controlIcon('list'), Eye = controlIcon('eye'), EyeOff = controlIcon('eye-off')
export const Lock = controlIcon('lock'), LockKeyhole = Lock, Globe = controlIcon('globe'), CalendarDays = controlIcon('calendar')
export const Copy = controlIcon('copy'), Pencil = controlIcon('pencil'), Trash2 = controlIcon('trash'), MoveRight = controlIcon('move')
export const FolderOpen = controlIcon('folder'), FileText = controlIcon('document'), Share2 = controlIcon('share')
export const Book = controlIcon('dictionary'), Dictionary = Book
export const Send = controlIcon('send'), Download = controlIcon('download'), Volume2 = controlIcon('volume')
export const RotateCcw = controlIcon('refresh'), Loader2Icon = controlIcon('loader'), LoaderCircle = Loader2Icon
export const AlertCircle = controlIcon('alert'), CircleCheckIcon = controlIcon('circle-check'), InfoIcon = controlIcon('info')
export const TriangleAlertIcon = controlIcon('triangle-alert'), OctagonXIcon = controlIcon('octagon-x')
export const Bold = controlIcon('bold'), Italic = controlIcon('italic'), Code2 = controlIcon('code')
export const Sun = controlIcon('sun'), Moon = controlIcon('moon')
export function Motif({ name, className, tone = 'color', ...props }: ArtProps & { name: MotifName }) {
  return <svg viewBox="0 0 160 120" fill="none" strokeWidth="1.3" className={cn('bauhaus-motif', className)} data-tone={tone} aria-hidden="true" {...props}>{motifs[name]}</svg>
}
export function BrandMark() {
  return (
    <svg viewBox="0 0 312 362" data-brand-mark className="size-8 shrink-0 max-[767px]:size-[25px]" aria-hidden="true">
      <path d="M0 93L188 2V49L48 117V268L0 291Z" fill={Y} />
      <path d="M62 128L250 37V84L110 152V303L62 326Z" fill={B} />
      <polygon points="124,163 312,72 312,270 124,361" fill={R} />
    </svg>
  )
}
