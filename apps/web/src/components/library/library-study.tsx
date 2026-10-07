'use client'

import Link from 'next/link'
import { Shape } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import type { StudySummary } from '@/lib/home-api'

const studyColors = {
  square: {
    title: 'text-art-blue',
    sub: 'text-art-blue/80 font-medium',
  },
  triangle: {
    title: 'text-art-yellow',
    sub: 'text-art-yellow/80 font-medium',
  },
  circle: {
    title: 'text-art-red',
    sub: 'text-art-red/80 font-medium',
  },
} as const

function StudyAction({ href, label, count, unit, shape }: { href: string; label: string; count: number; unit: string; shape: 'square' | 'triangle' | 'circle' }) {
  const colors = studyColors[shape]
  const content = (
    <>
      <span className="flex min-w-0 flex-col gap-1.5">
        <strong className={`text-xl font-extrabold leading-snug tracking-tight max-[1199px]:text-[19px] ${colors.title}`}>{label}</strong>
        <small className={`text-xs leading-normal ${colors.sub}`}>{count} {unit}</small>
      </span>
      <span className="pointer-events-none absolute right-4 top-1/2 flex -translate-y-1/2 items-center justify-center max-[767px]:right-3">
        <Shape name={shape} className="size-9 max-[1199px]:size-8 max-[767px]:size-7 shrink-0" />
      </span>
    </>
  )
  return <Button asChild={count > 0} disabled={count > 0 ? undefined : true} variant="outline" className="relative h-auto min-h-20 justify-start overflow-hidden py-3.5 pr-20 text-left whitespace-normal max-[1199px]:pr-[68px] max-[767px]:min-h-[60px] max-[767px]:py-2.5 max-[767px]:pr-14">{count > 0 ? <Link href={href}>{content}</Link> : content}</Button>
}

export function LibraryStudy({ summary, nodeId, publishedOwner }: { summary: StudySummary; nodeId: string; publishedOwner?: string }) {
  const owner = publishedOwner ? `&owner=${encodeURIComponent(publishedOwner)}` : ''
  return <div className="grid grid-cols-3 gap-3 py-4 max-[767px]:grid-cols-1 max-[767px]:gap-2" aria-label="Study actions">
    <StudyAction href={`/focus/flashcards?node=${encodeURIComponent(nodeId)}${owner}`} label="Flashcards" count={summary.total} unit="words" shape="square" />
    <StudyAction href={`/focus/learn?node=${encodeURIComponent(nodeId)}&selection=NEW${owner}`} label="Learn new" count={summary.new} unit="new" shape="triangle" />
    <StudyAction href={`/focus/learn?node=${encodeURIComponent(nodeId)}&selection=DUE${owner}`} label="Review" count={summary.due} unit="due" shape="circle" />
  </div>
}
