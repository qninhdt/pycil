'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Shape } from '@/components/artwork/artwork'
import { Button } from '@/components/ui/button'
import type { StudySummary } from '@/lib/api/study'

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

function StudyAction({
  href,
  label,
  count,
  unit,
  shape,
}: {
  href: string
  label: string
  count: number
  unit: string
  shape: 'square' | 'triangle' | 'circle'
}) {
  const colors = studyColors[shape]
  const content = (
    <>
      <div className="hidden md:flex min-w-0 flex-col gap-1.5">
        <strong className={`text-xl font-extrabold leading-snug tracking-tight max-[1199px]:text-[19px] ${colors.title}`}>
          {label}
        </strong>
        <small className={`text-xs leading-normal ${colors.sub}`}>
          {count} {unit}
        </small>
      </div>
      <span className="hidden md:flex pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 items-center justify-center max-[1199px]:right-3">
        <Shape name={shape} className="size-9 max-[1199px]:size-8 shrink-0" />
      </span>

      <div className="flex md:hidden flex-col items-start gap-1 w-full min-w-0">
        <div className="flex items-center justify-between w-full">
          <Shape name={shape} className="size-3.5 shrink-0" />
          <strong className={`text-xs font-extrabold tabular-nums ${colors.title}`}>
            {count}
          </strong>
        </div>
        <span className="text-[11px] font-bold leading-tight truncate w-full text-foreground">
          {label}
        </span>
      </div>
    </>
  )
  return (
    <Button
      asChild={count > 0}
      disabled={count > 0 ? undefined : true}
      variant="outline"
      aria-label={`${label}, ${count} ${unit}`}
      className="relative h-auto min-h-20 md:min-h-20 justify-start overflow-hidden py-3.5 pr-20 text-left whitespace-normal max-[1199px]:pr-[68px] max-[767px]:min-h-0 max-[767px]:py-2 max-[767px]:px-2.5 max-[767px]:pr-2.5 rounded-none"
    >
      {count > 0 ? <Link href={href}>{content}</Link> : content}
    </Button>
  )
}

export function LibraryStudy({
  summary,
  nodeId,
  publishedOwner,
}: {
  summary: StudySummary
  nodeId: string
  publishedOwner?: string
}) {
  const t = useTranslations('library')
  const tLearning = useTranslations('learning')
  const tCommon = useTranslations('common')
  const owner = publishedOwner ? `&owner=${encodeURIComponent(publishedOwner)}` : ''
  return (
    <div className="grid grid-cols-3 gap-2 sm:gap-3 py-2.5 sm:py-4" aria-label={t('studyActions')}>
      <StudyAction
        href={`/app/flashcards?node=${encodeURIComponent(nodeId)}${owner}`}
        label={tLearning('flashcards')}
        count={summary.total}
        unit={tCommon('words')}
        shape="square"
      />
      <StudyAction
        href={`/app/learn?node=${encodeURIComponent(nodeId)}&selection=new${owner}`}
        label={t('learnNew')}
        count={summary.new}
        unit={t('new').toLowerCase()}
        shape="triangle"
      />
      <StudyAction
        href={`/app/learn?node=${encodeURIComponent(nodeId)}&selection=auto${owner}`}
        label={t('practice')}
        count={summary.due > 0 ? summary.due : summary.total}
        unit={summary.due > 0 ? t('due').toLowerCase() : tCommon('words')}
        shape="circle"
      />
    </div>
  )
}
