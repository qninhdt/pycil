'use client'

import { useEffect, useRef, useState, type ReactNode, type SVGProps } from 'react'
import { cn } from '@/lib/utils'
import { backgroundCanvas } from '@/lib/background-layout'

const R = 'var(--art-red)', B = 'var(--art-blue)', Y = 'var(--art-yellow)'
const I = 'var(--art-ink)', P = 'var(--art-paper)'

// The original 16 hand-authored compositions, now anchored to an adaptive canvas.
// Motifs scale uniformly; only anchors and construction-rule lengths respond.
const backgrounds = {
  'archway-poster': (w, h) => <>
    <g transform={`translate(${w - 400} ${h - 240})`}><path d="M237 240V94a72 72 0 0 1 144 0v146Z" fill={R}/><path d="M271 240V94a38 38 0 0 1 76 0v146Z" fill={P}/><rect x="271" y="161" width="76" height="79" fill={B}/></g>
    <path d="M0 0h83L0 83Z" fill={Y}/><path d={`M${w - 197} 0v${h}M0 ${h - 79}h${w}`} stroke={I} opacity=".4"/>
  </>,
  'tangent-field': (w, h) => <>
    <g transform={`translate(${w - 400} 0)`}><circle cx="288" cy="91" r="77" fill={Y}/><circle cx="288" cy="91" r="47" fill={P}/><rect x="365" y="14" width="35" height="154" fill={B}/><circle cx="365" cy="168" r="25" fill={R}/></g>
    <path d={`M0 14h${w}M0 168h${w}M${w - 112} 0v${h}`} stroke={I} opacity=".4"/><rect x="22" y={h - 50} width="69" height="50" fill={B}/>
  </>,
  'stepped-horizon': (w, h) => <>
    <g transform={`translate(${w - 400} ${h - 240})`}><path d="M181 240v-61h55v-61h55V57h55V0h54v240Z" fill={B}/><path d="M236 240v-61h55v-61h55v-61h54v183Z" fill={Y}/><circle cx="248" cy="47" r="35" fill={R}/></g>
    <path d={`M0 ${h - 61}h${w}M${w - 219} 0v${h}`} stroke={I} opacity=".45"/>
  </>,
  'split-disc-field': (w, h) => <>
    <g transform={`translate(${w - 400} ${(h - 240) / 2})`}><path d="M285 18a97 97 0 0 0 0 194Z" fill={R}/><path d="M285 18a97 97 0 0 1 97 97h-97Z" fill={B}/><path d="M285 115h97a97 97 0 0 1-97 97Z" fill={Y}/></g>
    <path d={`M0 ${115 + (h - 240) / 2}h${w}M${w - 115} 0v${h}`} stroke={I} opacity=".4"/><rect x="19" y={h - 53} width="48" height="53" fill={B}/>
  </>,
  'suspended-orbits': (w, h) => <>
    <path d={`M${w - 212} 0v${h}M${w - 30} 0v${h}M0 ${h - 51}h${w}`} stroke={I} opacity=".4"/>
    <g transform={`translate(${w - 400} ${(h - 240) / 2})`}><circle cx="278" cy="88" r="67" stroke={I} fill="none"/><circle cx="278" cy="88" r="43" stroke={I} fill="none"/><circle cx="278" cy="45" r="26" fill={R}/><rect x="255" y="166" width="47" height="47" fill={B}/></g>
    <path d="M0 0h50L0 50Z" fill={Y}/>
  </>,
  'cantilever-field': (w, h) => <>
    <g transform={`translate(${w - 400} ${(h - 240) / 2})`}><rect x="194" y="31" width="206" height="48" fill={B}/><rect x="267" y="79" width="48" height="161" fill={R}/><path d="m360 122 40 118h-80Z" fill={Y}/></g>
    <path d={`M0 ${79 + (h - 240) / 2}h${w}M${w - 133} 0v${h}`} stroke={I} opacity=".4"/><circle cx="41" cy={h - 37} r="21" stroke={I} fill="none"/>
  </>,
  'window-study': (w, h) => <>
    <g transform={`translate(${w - 400} ${(h - 240) / 2})`}><rect x="219" y="25" width="146" height="190" fill={B}/><path d="M249 215V91a43 43 0 0 1 86 0v124Z" fill={P}/><circle cx="360" cy="47" r="27" fill={R}/></g>
    <path d={`M0 ${h}h77L0 ${h - 77}Z`} fill={Y}/><path d={`M0 ${159 + (h - 240) / 2}h${w}M${w - 108} 0v${h}`} stroke={I} opacity=".4"/>
  </>,
  'quiet-tangents': (w, h) => <>
    <g transform={`translate(${w - 400} ${(h - 240) / 2})`}><circle cx="296" cy="119" r="76" stroke={I} fill="none"/><circle cx="296" cy="119" r="48" stroke={I} fill="none"/><circle cx="372" cy="119" r="11" fill={R}/></g>
    <path d={`M0 ${43 + (h - 240) / 2}h${w}M0 ${195 + (h - 240) / 2}h${w}M${w - 180} 0v${h}M${w - 28} 0v${h}`} stroke={I} opacity=".35"/>
    <rect x="17" y={h - 38} width="20" height="20" fill={B}/><path d={`m63 ${h - 38} 11 20H52Z`} fill={Y}/>
  </>,
  'primary-poster': (w, h) => <>
    <circle cx={w - 114} cy="90" r="83" fill={R}/><rect x="25" y={h - 90} width="77" height="90" fill={B}/>
    <path d={`M${w} ${h - 163}v163H${w - 252}Z`} fill={Y}/><path d={`M0 91h${w}M102 0v${h}M${w - 114} 0v${h}M0 ${h - 64}h${w}`} stroke={I} opacity=".5"/>
    <path d={`M${w - 113} ${h}a75 75 0 0 1 113-65`} stroke={I} fill="none"/>
  </>,
  'editorial-axis': (w, h) => <>
    <path d={`M0 80h${w}M${w - 151} 0v${h}M92 0v${h}`} stroke={I} opacity=".5"/>
    <g transform={`translate(${w - 400} ${(h - 240) / 2})`}><path d="M249 17v179A89.5 89.5 0 0 1 249 17Z" fill={R}/><rect x="249" y="17" width="69" height="179" fill={B}/></g><circle cx="63" cy={h - 38} r="18" fill={Y}/>
  </>,
  'corner-study': (w, h) => <>
    <path d={`M${w} 0v122A122 122 0 0 1 ${w - 122} 0Z`} fill={R}/><rect x="0" y={h - 94} width="74" height="94" fill={B}/><path d="M0 0h88L0 88Z" fill={Y}/>
    <path d={`M37 ${h - 112}v112M0 ${h - 38}h115M${w - 54} 0v159`} stroke={I} opacity=".5"/>
  </>,
  'modular-field': (w, h) => <>
    <g transform={`translate(${w - 400} ${(h - 240) / 2})`}><rect x="222" y="20" width="74" height="74" fill={B}/><path d="M370 20v74h-74a74 74 0 0 1 74-74" fill={R}/><path d="M222 94h74v74Z" fill={Y}/><circle cx="333" cy="131" r="37" stroke={I} fill="none"/></g>
    <path d={`M${w - 197} 0v${h}M0 ${h - 52}h${w}`} stroke={I} opacity=".4"/><rect x="24" y={h - 52} width="60" height="52" fill={R}/>
  </>,
  'orbital-field': (w, h) => <>
    <g transform={`translate(${w - 400} ${(h - 240) / 2})`}><circle cx="296" cy="125" r="83" stroke={I} fill="none"/><circle cx="296" cy="125" r="54" stroke={I} fill="none"/><circle cx="251" cy="58" r="38" fill={B}/><circle cx="296" cy="125" r="20" fill={R}/><rect x="333" y="167" width="44" height="44" fill={Y}/></g>
    <path d={`M0 ${125 + (h - 240) / 2}h${w}`} stroke={I} opacity=".4"/>
  </>,
  'diagonal-plane': (w, h) => <>
    <g transform={`translate(${w - 400} ${h - 240})`}><path d="M185 240 400 25v215Z" fill={Y}/><path d="M400 240H287L400 127Z" fill={B}/><circle cx="275" cy="54" r="43" fill={R}/><path d="M165 240 400 5" stroke={I} opacity=".5"/></g>
    <path d={`M0 ${h - 142}h${w}M${w - 67} 0v${h}`} stroke={I} opacity=".5"/>
  </>,
  'quiet-construction': (w, h) => <>
    <g transform={`translate(${w - 400} ${(h - 240) / 2})`}><rect x="230" y="29" width="120" height="120" fill="none" stroke={I}/><circle cx="285" cy="102" r="65" stroke={I} fill="none"/><path d="M185 102h215" stroke={I} opacity=".35"/><circle cx="350" cy="149" r="14" fill={R}/></g>
    <path d={`M${w - 115} 0v${h}`} stroke={I} opacity=".35"/><path d={`M20 ${h - 26}h99`} stroke={I}/>
  </>,
  'inverse-poster': (w, h) => <>
    <g transform={`translate(${w - 400} ${(h - 240) / 2})`}><path d="M263 0a105 105 0 0 0 0 210Z" fill={Y}/><rect x="263" y="0" width="76" height="210" fill={B}/></g>
    <circle cx="54" cy={h - 63} r="38" fill={R}/><path d={`M0 ${103 + (h - 240) / 2}h${w}M${w - 137} 0v${h}`} stroke={I} opacity=".65"/>
  </>,
} satisfies Record<string, (width: number, height: number) => ReactNode>

export type BackgroundName = keyof typeof backgrounds
export const backgroundNames = Object.keys(backgrounds) as BackgroundName[]
type BackgroundProps = Omit<SVGProps<SVGSVGElement>, 'name' | 'viewBox' | 'preserveAspectRatio' | 'children' | 'ref'> & { name: BackgroundName; tone?: 'color' | 'mono' }

export function Background({ name, className, tone = 'color', ...props }: BackgroundProps) {
  const ref = useRef<SVGSVGElement>(null)
  const [canvas, setCanvas] = useState({ width: 400, height: 240 })
  useEffect(() => {
    const svg = ref.current
    if (!svg) return
    const resize = (width: number, height: number) => {
      if (width <= 0 || height <= 0) return
      const next = backgroundCanvas(width, height)
      setCanvas(current => Math.abs(current.width - next.width) < .01 && Math.abs(current.height - next.height) < .01 ? current : next)
    }
    const bounds = svg.getBoundingClientRect()
    resize(bounds.width, bounds.height)
    const observer = new ResizeObserver(entries => { const { width, height } = entries[0].contentRect; resize(width, height) })
    observer.observe(svg)
    return () => observer.disconnect()
  }, [])
  return <svg {...props} ref={ref} width="100%" height="100%" viewBox={`0 0 ${canvas.width} ${canvas.height}`} preserveAspectRatio="xMidYMid meet"
    fill="none" strokeWidth="1" className={cn('bauhaus-background', className)} data-tone={tone} data-background={name} aria-hidden="true">
    <rect data-background-canvas="" width={canvas.width} height={canvas.height} fill={P}/>
    {backgrounds[name](canvas.width, canvas.height)}
  </svg>
}
